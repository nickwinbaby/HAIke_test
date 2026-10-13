using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;

internal static class PaneLogger
{
    private const uint ATTACH_PARENT_PROCESS = 0xFFFFFFFF;
    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool AttachConsole(uint processId);

    private sealed class ChildJob : IDisposable
    {
        private const uint JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000;
        private const int JobObjectExtendedLimitInformation = 9;

        [StructLayout(LayoutKind.Sequential)]
        private struct JOBOBJECT_BASIC_LIMIT_INFORMATION
        {
            public long PerProcessUserTimeLimit, PerJobUserTimeLimit;
            public uint LimitFlags;
            public UIntPtr MinimumWorkingSetSize, MaximumWorkingSetSize;
            public uint ActiveProcessLimit;
            public long Affinity;
            public uint PriorityClass, SchedulingClass;
        }

        [StructLayout(LayoutKind.Sequential)]
        private struct IO_COUNTERS
        {
            public ulong ReadOperationCount, WriteOperationCount, OtherOperationCount;
            public ulong ReadTransferCount, WriteTransferCount, OtherTransferCount;
        }

        [StructLayout(LayoutKind.Sequential)]
        private struct JOBOBJECT_EXTENDED_LIMIT_INFORMATION
        {
            public JOBOBJECT_BASIC_LIMIT_INFORMATION BasicLimitInformation;
            public IO_COUNTERS IoInfo;
            public UIntPtr ProcessMemoryLimit, JobMemoryLimit, PeakProcessMemoryUsed, PeakJobMemoryUsed;
        }

        [DllImport("kernel32.dll", CharSet = CharSet.Unicode)]
        private static extern IntPtr CreateJobObject(IntPtr attributes, string name);
        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern bool SetInformationJobObject(IntPtr job, int infoClass, IntPtr info, uint length);
        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern bool AssignProcessToJobObject(IntPtr job, IntPtr process);
        [DllImport("kernel32.dll")]
        private static extern bool CloseHandle(IntPtr handle);

        private IntPtr handle;

        public ChildJob(Process process)
        {
            handle = CreateJobObject(IntPtr.Zero, null);
            if (handle == IntPtr.Zero) return;
            JOBOBJECT_EXTENDED_LIMIT_INFORMATION info = new JOBOBJECT_EXTENDED_LIMIT_INFORMATION();
            info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
            int size = Marshal.SizeOf(info);
            IntPtr memory = Marshal.AllocHGlobal(size);
            try
            {
                Marshal.StructureToPtr(info, memory, false);
                if (!SetInformationJobObject(handle, JobObjectExtendedLimitInformation, memory, (uint)size) ||
                    !AssignProcessToJobObject(handle, process.Handle))
                {
                    CloseHandle(handle); handle = IntPtr.Zero;
                }
            }
            finally { Marshal.FreeHGlobal(memory); }
        }

        public void Dispose()
        {
            if (handle != IntPtr.Zero) { CloseHandle(handle); handle = IntPtr.Zero; }
        }
    }

    private static string Quote(string value)
    {
        if (String.IsNullOrEmpty(value)) return "\"\"";
        if (value.IndexOfAny(new char[] { ' ', '\t', '\n', '\v', '"' }) < 0) return value;
        StringBuilder result = new StringBuilder("\"");
        int slashes = 0;
        foreach (char c in value)
        {
            if (c == '\\') slashes++;
            else if (c == '"')
            {
                result.Append('\\', slashes * 2 + 1);
                result.Append('"');
                slashes = 0;
            }
            else
            {
                result.Append('\\', slashes);
                slashes = 0;
                result.Append(c);
            }
        }
        result.Append('\\', slashes * 2);
        result.Append('"');
        return result.ToString();
    }

    private static void CopyAndLog(Stream source, Stream destination, FileStream log, object logLock)
    {
        byte[] buffer = new byte[8192];
        try
        {
            int read;
            while ((read = source.Read(buffer, 0, buffer.Length)) > 0)
            {
                lock (logLock)
                {
                    log.Write(buffer, 0, read);
                    log.Flush();
                }
                try
                {
                    destination.Write(buffer, 0, read);
                    destination.Flush();
                }
                catch { }
            }
        }
        catch { }
    }

    public static int Run(string[] args)
    {
        // The combined application is a WinExe. In logger mode it must attach
        // to the Windows Terminal parent console so keyboard input and live
        // output continue to work inside the pane.
        bool attachedToTerminal = AttachConsole(ATTACH_PARENT_PROCESS);
        string logPath = null;
        int separator = -1;
        for (int i = 0; i < args.Length; i++)
        {
            if (args[i] == "--log" && i + 1 < args.Length)
            {
                logPath = args[++i];
                continue;
            }
            if (args[i] == "--")
            {
                separator = i;
                break;
            }
        }
        if (String.IsNullOrWhiteSpace(logPath) || separator < 0 || separator + 1 >= args.Length) return 2;

        try
        {
            logPath = Path.GetFullPath(logPath);
            Directory.CreateDirectory(Path.GetDirectoryName(logPath));

            string executable = args[separator + 1];
            List<string> childArgs = new List<string>();
            for (int i = separator + 2; i < args.Length; i++) childArgs.Add(args[i]);

            string extension = Path.GetExtension(executable).ToLowerInvariant();
            if (extension == ".cmd" || extension == ".bat")
            {
                childArgs.Insert(0, executable);
                childArgs.Insert(0, "/c");
                childArgs.Insert(0, "/d");
                executable = Environment.GetEnvironmentVariable("ComSpec") ?? "cmd.exe";
            }

            StringBuilder argumentText = new StringBuilder();
            foreach (string arg in childArgs)
            {
                if (argumentText.Length > 0) argumentText.Append(' ');
                argumentText.Append(Quote(arg));
            }

            Process child = new Process();
            child.StartInfo = new ProcessStartInfo
            {
                FileName = executable,
                Arguments = argumentText.ToString(),
                UseShellExecute = false,
                CreateNoWindow = true,
                RedirectStandardInput = true,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                WorkingDirectory = Environment.CurrentDirectory
            };
            child.Start();

            object logLock = new object();
            using (ChildJob childJob = new ChildJob(child))
            using (FileStream log = new FileStream(logPath, FileMode.Append, FileAccess.Write, FileShare.ReadWrite))
            {
                byte[] start = Encoding.UTF8.GetBytes("[日志开始] " + DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss.fff") + "\r\n");
                log.Write(start, 0, start.Length);
                log.Flush();

                Stream screen = Console.OpenStandardOutput();
                Thread output = new Thread(new ThreadStart(delegate { CopyAndLog(child.StandardOutput.BaseStream, screen, log, logLock); }));
                Thread error = new Thread(new ThreadStart(delegate { CopyAndLog(child.StandardError.BaseStream, screen, log, logLock); }));
                output.IsBackground = true;
                error.IsBackground = true;
                output.Start();
                error.Start();

                Thread input = new Thread(new ThreadStart(delegate
                {
                    try
                    {
                        Stream keyboard = Console.OpenStandardInput();
                        Stream childInput = child.StandardInput.BaseStream;
                        byte[] buffer = new byte[4096];
                        int read;
                        while (!child.HasExited && (read = keyboard.Read(buffer, 0, buffer.Length)) > 0)
                        {
                            childInput.Write(buffer, 0, read);
                            childInput.Flush();
                        }
                    }
                    catch { }
                    finally
                    {
                        // Closing a Terminal pane closes its input stream. The
                        // child shell uses -NoExit, so explicitly terminate it
                        // on EOF; otherwise both logger and shell stay orphaned.
                        if (attachedToTerminal && !child.HasExited) try { child.Kill(); } catch { }
                    }
                }));
                input.IsBackground = true;
                input.Start();

                child.WaitForExit();
                output.Join(3000);
                error.Join(3000);

                byte[] end = Encoding.UTF8.GetBytes("\r\n[日志结束] " + DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss.fff") + " 退出码=" + child.ExitCode + "\r\n");
                lock (logLock)
                {
                    log.Write(end, 0, end.Length);
                    log.Flush();
                }
            }
            return child.ExitCode;
        }
        catch (Exception ex)
        {
            try { File.AppendAllText(logPath, "\r\n[日志组件错误] " + ex + "\r\n", Encoding.UTF8); } catch { }
            return 9;
        }
    }
}

internal static class ProcessTree
{
    private const uint TH32CS_SNAPPROCESS = 0x00000002;
    private static readonly IntPtr InvalidHandle = new IntPtr(-1);

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Auto)]
    private struct PROCESSENTRY32
    {
        public uint dwSize, cntUsage, th32ProcessID;
        public IntPtr th32DefaultHeapID;
        public uint th32ModuleID, cntThreads, th32ParentProcessID;
        public int pcPriClassBase;
        public uint dwFlags;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 260)] public string szExeFile;
    }

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern IntPtr CreateToolhelp32Snapshot(uint flags, uint processId);
    [DllImport("kernel32.dll", CharSet = CharSet.Auto, SetLastError = true)]
    private static extern bool Process32First(IntPtr snapshot, ref PROCESSENTRY32 entry);
    [DllImport("kernel32.dll", CharSet = CharSet.Auto, SetLastError = true)]
    private static extern bool Process32Next(IntPtr snapshot, ref PROCESSENTRY32 entry);
    [DllImport("kernel32.dll")] private static extern bool CloseHandle(IntPtr handle);

    public static Dictionary<int, int> Snapshot()
    {
        Dictionary<int, int> result = new Dictionary<int, int>();
        IntPtr snapshot = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
        if (snapshot == IntPtr.Zero || snapshot == InvalidHandle) return result;
        try
        {
            PROCESSENTRY32 entry = new PROCESSENTRY32(); entry.dwSize = (uint)Marshal.SizeOf(entry);
            if (Process32First(snapshot, ref entry))
                do { result[(int)entry.th32ProcessID] = (int)entry.th32ParentProcessID; } while (Process32Next(snapshot, ref entry));
        }
        finally { CloseHandle(snapshot); }
        return result;
    }

    public static int ParentProcessId(int processId)
    {
        int parent; return Snapshot().TryGetValue(processId, out parent) ? parent : 0;
    }

    public static bool IsAlive(int processId)
    {
        try { using (Process process = Process.GetProcessById(processId)) return !process.HasExited; } catch { return false; }
    }

    public static bool ParentIsAlive(int processId)
    {
        int parent = ParentProcessId(processId); return parent > 0 && IsAlive(parent);
    }

    public static List<int> Descendants(int rootId)
    {
        Dictionary<int, int> snapshot = Snapshot(); List<int> result = new List<int>();
        bool changed = true;
        while (changed)
        {
            changed = false;
            foreach (KeyValuePair<int, int> pair in snapshot)
                if (!result.Contains(pair.Key) && (pair.Value == rootId || result.Contains(pair.Value))) { result.Add(pair.Key); changed = true; }
        }
        return result;
    }

    public static bool KillTree(int rootId)
    {
        List<int> ids = Descendants(rootId); ids.Reverse(); ids.Add(rootId);
        foreach (int id in ids)
        {
            try
            {
                using (Process process = Process.GetProcessById(id))
                {
                    process.Kill();
                    process.WaitForExit(3000);
                }
            }
            catch { }
        }
        foreach (int id in ids) if (IsAlive(id)) return false;
        return true;
    }
}

internal static class ProcessCommandLine
{
    public static string Read(int processId)
    {
        try
        {
            using (System.Management.ManagementObjectSearcher searcher = new System.Management.ManagementObjectSearcher(
                "SELECT CommandLine FROM Win32_Process WHERE ProcessId = " + processId))
            using (System.Management.ManagementObjectCollection objects = searcher.Get())
                foreach (System.Management.ManagementObject item in objects)
                    using (item) return Convert.ToString(item["CommandLine"]);
        }
        catch { }
        return "";
    }
}
