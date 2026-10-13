using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using System.Windows.Forms;

[assembly: AssemblyTitle("powershell 分屏工作台 V1.3.1 - Mangetic - 2026-9-11")]
[assembly: AssemblyDescription("Windows Terminal PowerShell 多窗口分屏配置工具")]
[assembly: AssemblyCompany("Mangetic")]
[assembly: AssemblyProduct("powershell 分屏工作台 V1.3.1 - Mangetic - 2026-9-11")]
[assembly: AssemblyCopyright("Copyright © 2026")]
[assembly: AssemblyVersion("1.3.1.0")]
[assembly: AssemblyFileVersion("1.3.1.0")]

internal sealed class OptionItem
{
    public string Key { get; private set; }
    public string Text { get; private set; }
    public OptionItem(string key, string text) { Key = key; Text = text; }
    public override string ToString() { return Text; }
}

internal static class WtCommand
{
    public static readonly Dictionary<int, OptionItem[]> Layouts = new Dictionary<int, OptionItem[]>
    {
        { 2, new[] { new OptionItem("columns", "左右并排"), new OptionItem("rows", "上下并排") } },
        { 3, new[] {
            new OptionItem("row", "左右三列"), new OptionItem("column", "上下三行"),
            new OptionItem("left-large", "左大、右侧上下两个小窗口"),
            new OptionItem("right-large", "右大、左侧上下两个小窗口") } },
        { 4, new[] { new OptionItem("grid", "2 × 2 十字型") } },
        { 5, new[] { new OptionItem("grid-3-2", "上三下二"), new OptionItem("grid-2-3", "上二下三") } },
        { 6, new[] { new OptionItem("grid-3x2", "三列两行") } }
    };

    private static void AddShell(List<string> a, string shell, IList<string> customArgs, string logPath)
    {
        List<string> shellArgs = new List<string>();
        string shellName = Path.GetFileName(shell).ToLowerInvariant();
        bool isPowerShell = shellName == "powershell.exe" || shellName == "pwsh.exe";
        if (shellName == "powershell.exe" || shellName == "pwsh.exe")
        { shellArgs.Add("-NoLogo"); shellArgs.Add("-NoExit"); }
        else if (shellName == "bash.exe" && (customArgs == null || customArgs.Count == 0))
        { shellArgs.Add("--login"); shellArgs.Add("-i"); }
        if (isPowerShell)
        {
            AddPowerShell(a, shell, shellArgs, customArgs, logPath);
            return;
        }
        if (customArgs != null) foreach (string arg in customArgs) shellArgs.Add(arg);
        if (String.IsNullOrWhiteSpace(logPath))
        {
            a.Add(shell); foreach (string arg in shellArgs) a.Add(arg); return;
        }

        a.Add(PaneLoggerPath); a.Add("--pane-logger"); a.Add("--log"); a.Add(logPath); a.Add("--"); a.Add(shell);
        foreach (string arg in shellArgs) a.Add(arg);
    }

    private static void AddPowerShell(List<string> a, string shell, List<string> baseArgs, IList<string> customArgs, string logPath)
    {
        List<string> args = customArgs == null ? new List<string>() : new List<string>(customArgs);
        int commandIndex = FindArgument(args, "-Command", "-c");
        int fileIndex = FindArgument(args, "-File", "-f");
        int encodedIndex = FindArgument(args, "-EncodedCommand", "-e", "-ec");
        string userCommand = "";
        int specialIndex = commandIndex >= 0 ? commandIndex : (fileIndex >= 0 ? fileIndex : encodedIndex);
        if (specialIndex >= 0)
        {
            if (commandIndex >= 0)
                userCommand = JoinCommandTokens(args, specialIndex + 1);
            else if (fileIndex >= 0 && specialIndex + 1 < args.Count)
            {
                userCommand = "& " + PowerShellLiteral(args[specialIndex + 1]);
                for (int i = specialIndex + 2; i < args.Count; i++) userCommand += " " + PowerShellLiteral(args[i]);
            }
            else if (encodedIndex >= 0 && specialIndex + 1 < args.Count)
            {
                try { userCommand = DecodePowerShellCommand(args[specialIndex + 1]); }
                catch { throw new InvalidOperationException("PowerShell 的 -EncodedCommand 不是有效的 Base64 UTF-16LE 内容。"); }
            }
            args.RemoveRange(specialIndex, args.Count - specialIndex);
        }

        if (String.IsNullOrWhiteSpace(logPath) && specialIndex < 0)
        {
            a.Add(shell); foreach (string arg in baseArgs) a.Add(arg); foreach (string arg in args) a.Add(arg);
            return;
        }

        // Windows Terminal parses semicolons as command separators even when
        // they originate inside a nested PowerShell command argument. Encode
        // the whole script so wt.exe sees one opaque argument and cannot turn
        // the user's command (for example "dir") into an extra tab.
        string script = String.IsNullOrWhiteSpace(logPath)
            ? userCommand
            : "Start-Transcript -LiteralPath '" + logPath.Replace("'", "''") + "' -Append | Out-Null";
        if (!String.IsNullOrWhiteSpace(logPath) && !String.IsNullOrWhiteSpace(userCommand)) script += "; " + userCommand;
        // On this Windows Terminal/Windows PowerShell combination, combining
        // -NoExit with -Command, -File or -EncodedCommand starts the process
        // but leaves the startup script unexecuted. Run the encoded script
        // without -NoExit and enter a nested interactive prompt afterwards.
        // This keeps the pane open while hiding script semicolons from wt.exe.
        script += "; $host.EnterNestedPrompt()";
        baseArgs.RemoveAll(delegate(string arg) { return String.Equals(arg, "-NoExit", StringComparison.OrdinalIgnoreCase); });
        if (FindArgument(baseArgs, "-NoProfile", "-nopro") < 0 && FindArgument(args, "-NoProfile", "-nopro") < 0)
            baseArgs.Add("-NoProfile");
        a.Add(shell); foreach (string arg in baseArgs) a.Add(arg); foreach (string arg in args) a.Add(arg);
        a.Add("-EncodedCommand");
        a.Add(EncodePowerShellCommand(script));
    }

    public static string EncodePowerShellCommand(string script)
    {
        return Convert.ToBase64String(Encoding.Unicode.GetBytes(script ?? ""));
    }

    public static string DecodePowerShellCommand(string encoded)
    {
        return Encoding.Unicode.GetString(Convert.FromBase64String(encoded ?? ""));
    }

    public static int CountEncodedCommandsContaining(IList<string> args, string text)
    {
        int count = 0;
        for (int i = 0; i + 1 < args.Count; i++)
            if (String.Equals(args[i], "-EncodedCommand", StringComparison.OrdinalIgnoreCase) &&
                DecodePowerShellCommand(args[i + 1]).IndexOf(text, StringComparison.OrdinalIgnoreCase) >= 0) count++;
        return count;
    }

    private static int FindArgument(IList<string> args, params string[] names)
    {
        for (int i = 0; i < args.Count; i++)
            foreach (string name in names)
                if (String.Equals(args[i], name, StringComparison.OrdinalIgnoreCase)) return i;
        return -1;
    }

    private static string JoinCommandTokens(IList<string> args, int start)
    {
        if (start >= args.Count) return "";
        if (start == args.Count - 1) return args[start];
        List<string> values = new List<string>();
        for (int i = start; i < args.Count; i++) values.Add(args[i]);
        return String.Join(" ", values.ToArray());
    }

    private static string PowerShellLiteral(string value)
    {
        return "'" + (value ?? "").Replace("'", "''") + "'";
    }

    public static string PaneLoggerPath
    {
        get { return Assembly.GetExecutingAssembly().Location; }
    }

    private static void Pane(List<string> a, string dir, string shell, IList<string> shellArgs, string logPath)
    {
        if (!String.IsNullOrWhiteSpace(dir)) { a.Add("-d"); a.Add(dir); }
        AddShell(a, shell, shellArgs, logPath);
    }

    private static void Split(List<string> a, string direction, string dir, string shell, IList<string> shellArgs, string size, string logPath)
    {
        a.Add(";"); a.Add("split-pane"); a.Add(direction);
        if (!String.IsNullOrEmpty(size)) { a.Add("--size"); a.Add(size); }
        Pane(a, dir, shell, shellArgs, logPath);
    }

    private static void Focus(List<string> a, string direction)
    {
        a.Add(";"); a.Add("move-focus"); a.Add(direction);
    }

    public static List<string> Build(int count, string layout, IList<string> dirs, string shell, string target, IList<string> logPaths = null, IList<string> shellArgs = null)
    {
        if (!Layouts.ContainsKey(count)) throw new ArgumentException("窗口数量必须为 2 到 6。");
        bool valid = false;
        foreach (OptionItem item in Layouts[count]) if (item.Key == layout) valid = true;
        if (!valid) throw new ArgumentException("当前窗口数量不支持所选布局。");

        string[] d = new string[count];
        for (int i = 0; i < count; i++) d[i] = i < dirs.Count ? dirs[i] : "";
        string[] logs = new string[count];
        for (int i = 0; i < count; i++) logs[i] = logPaths != null && i < logPaths.Count ? logPaths[i] : "";
        List<string> a = new List<string> { "-w", String.IsNullOrWhiteSpace(target) ? "new" : target, "new-tab" };
        Pane(a, d[0], shell, shellArgs, logs[0]);

        if (count == 2)
            Split(a, layout == "columns" ? "-V" : "-H", d[1], shell, shellArgs, null, logs[1]);
        else if (count == 3 && layout == "row")
        {
            Split(a, "-V", d[1], shell, shellArgs, "0.666667", logs[1]); Split(a, "-V", d[2], shell, shellArgs, "0.5", logs[2]);
        }
        else if (count == 3 && layout == "column")
        {
            Split(a, "-H", d[1], shell, shellArgs, "0.666667", logs[1]); Split(a, "-H", d[2], shell, shellArgs, "0.5", logs[2]);
        }
        else if (count == 3 && layout == "left-large")
        {
            Split(a, "-V", d[1], shell, shellArgs, null, logs[1]); Split(a, "-H", d[2], shell, shellArgs, null, logs[2]);
        }
        else if (count == 3)
        {
            Split(a, "-V", d[2], shell, shellArgs, null, logs[2]); Focus(a, "left"); Split(a, "-H", d[1], shell, shellArgs, null, logs[1]);
        }
        else if (count == 4)
        {
            // Build the bottom row first, then split the full-width top pane.
            // A single unambiguous upward focus move prevents an occasional
            // 1-pane-left/3-panes-right result from repeated lateral moves.
            Split(a, "-H", d[2], shell, shellArgs, null, logs[2]); Split(a, "-V", d[3], shell, shellArgs, null, logs[3]);
            Focus(a, "up"); Split(a, "-V", d[1], shell, shellArgs, null, logs[1]);
        }
        else if (count == 5 && layout == "grid-3-2")
        {
            Split(a, "-H", d[3], shell, shellArgs, null, logs[3]); Split(a, "-V", d[4], shell, shellArgs, null, logs[4]); Focus(a, "up");
            Split(a, "-V", d[1], shell, shellArgs, "0.666667", logs[1]); Split(a, "-V", d[2], shell, shellArgs, "0.5", logs[2]);
        }
        else if (count == 5)
        {
            Split(a, "-H", d[2], shell, shellArgs, null, logs[2]); Focus(a, "up"); Split(a, "-V", d[1], shell, shellArgs, null, logs[1]);
            Focus(a, "down"); Split(a, "-V", d[3], shell, shellArgs, "0.666667", logs[3]); Split(a, "-V", d[4], shell, shellArgs, "0.5", logs[4]);
        }
        else
        {
            Split(a, "-H", d[3], shell, shellArgs, null, logs[3]); Split(a, "-V", d[4], shell, shellArgs, "0.666667", logs[4]);
            Split(a, "-V", d[5], shell, shellArgs, "0.5", logs[5]); Focus(a, "up");
            Split(a, "-V", d[1], shell, shellArgs, "0.666667", logs[1]); Split(a, "-V", d[2], shell, shellArgs, "0.5", logs[2]);
        }
        return a;
    }

    [DllImport("shell32.dll", SetLastError = true)]
    private static extern IntPtr CommandLineToArgvW([MarshalAs(UnmanagedType.LPWStr)] string commandLine, out int argumentCount);

    [DllImport("kernel32.dll")]
    private static extern IntPtr LocalFree(IntPtr memory);

    public static List<string> ParseArguments(string text)
    {
        List<string> result = new List<string>();
        if (String.IsNullOrWhiteSpace(text)) return result;
        int count; IntPtr argv = CommandLineToArgvW("placeholder.exe " + text, out count);
        if (argv == IntPtr.Zero) throw new InvalidOperationException("启动参数格式无法解析。请检查双引号是否成对。");
        try
        {
            for (int i = 1; i < count; i++)
                result.Add(Marshal.PtrToStringUni(Marshal.ReadIntPtr(argv, i * IntPtr.Size)));
        }
        finally { LocalFree(argv); }
        return result;
    }

    public static List<string> ParseShellInput(string shell, string text)
    {
        string value = (text ?? "").Trim();
        string shellName = Path.GetFileName(shell ?? "").ToLowerInvariant();
        bool isPowerShell = shellName == "powershell.exe" || shellName == "pwsh.exe";
        if (isPowerShell && value.Length > 0 && !value.StartsWith("-", StringComparison.Ordinal))
            return new List<string> { "-Command", value };
        return ParseArguments(value);
    }

    public static List<string> BuildStartupArguments(string shell, string commandText)
    {
        string command = (commandText ?? "").Trim();
        if (command.Length == 0) return new List<string>();
        string name = Path.GetFileName(shell ?? "").ToLowerInvariant();
        if (name == "powershell.exe" || name == "pwsh.exe")
            return new List<string> { "-Command", command };
        if (name == "cmd.exe")
            return new List<string> { "/d", "/k", command };
        if (name == "bash.exe")
            // Avoid a literal semicolon: wt.exe also treats it as a command
            // separator and could create an unintended extra pane/tab. The
            // left-associative shell expression always reaches the final exec.
            return new List<string> { "--login", "-i", "-c", command + " || : && exec bash --login -i" };
        if (name == "python.exe" || name == "python3.exe" || name == "py.exe")
            return new List<string> { "-i", "-c", command };
        // Other programs keep argument-style compatibility. For example:
        // adb.exe with "-s DEVICE_SERIAL shell".
        return ParseArguments(command);
    }

    public static string Quote(string value)
    {
        if (value == null) return "\"\"";
        if (value.Length > 0 && value.IndexOfAny(new char[] { ' ', '\t', '\n', '\v', '"' }) < 0) return value;
        StringBuilder b = new StringBuilder("\"");
        int slashes = 0;
        foreach (char c in value)
        {
            if (c == '\\') slashes++;
            else if (c == '"') { b.Append('\\', slashes * 2 + 1); b.Append('"'); slashes = 0; }
            else { b.Append('\\', slashes); slashes = 0; b.Append(c); }
        }
        b.Append('\\', slashes * 2); b.Append('"');
        return b.ToString();
    }

    public static string Join(IEnumerable<string> args)
    {
        List<string> result = new List<string>();
        foreach (string arg in args) result.Add(Quote(arg));
        return String.Join(" ", result.ToArray());
    }

    public static List<List<string>> BuildSteps(List<string> command, string target)
    {
        List<List<string>> steps = new List<List<string>>();
        List<string> current = new List<string>();
        foreach (string arg in command)
        {
            if (arg == ";")
            {
                if (current.Count > 0) steps.Add(current);
                current = new List<string> { "-w", target };
            }
            else current.Add(arg);
        }
        if (current.Count > 0) steps.Add(current);
        return steps;
    }

}

internal sealed class LayoutPreview : Control
{
    public int PaneCount = 4;
    public string LayoutKey = "grid";
    public LayoutPreview() { DoubleBuffered = true; BackColor = Color.White; MinimumSize = new Size(200, 105); }

    private void DrawPane(Graphics g, RectangleF r, int n)
    {
        r.Inflate(-2, -2);
        using (Brush fill = new SolidBrush(Color.FromArgb(232, 241, 253))) g.FillRectangle(fill, r);
        using (Pen pen = new Pen(Color.FromArgb(70, 116, 180), 1.5f)) g.DrawRectangle(pen, r.X, r.Y, r.Width, r.Height);
        using (Font f = new Font(Font.FontFamily, 10, FontStyle.Bold))
        using (Brush text = new SolidBrush(Color.FromArgb(45, 78, 123)))
        {
            SizeF s = g.MeasureString(n.ToString(), f);
            g.DrawString(n.ToString(), f, text, r.X + (r.Width - s.Width) / 2, r.Y + (r.Height - s.Height) / 2);
        }
    }

    protected override void OnPaint(PaintEventArgs e)
    {
        base.OnPaint(e);
        float x = 4, y = 4, w = Width - 8, h = Height - 8;
        if (PaneCount == 2 && LayoutKey == "rows")
        { DrawPane(e.Graphics, new RectangleF(x, y, w, h / 2), 1); DrawPane(e.Graphics, new RectangleF(x, y + h / 2, w, h / 2), 2); }
        else if (PaneCount == 2)
        { DrawPane(e.Graphics, new RectangleF(x, y, w / 2, h), 1); DrawPane(e.Graphics, new RectangleF(x + w / 2, y, w / 2, h), 2); }
        else if (PaneCount == 3 && LayoutKey == "column")
            for (int i = 0; i < 3; i++) DrawPane(e.Graphics, new RectangleF(x, y + h * i / 3, w, h / 3), i + 1);
        else if (PaneCount == 3 && LayoutKey == "left-large")
        { DrawPane(e.Graphics, new RectangleF(x, y, w / 2, h), 1); DrawPane(e.Graphics, new RectangleF(x + w / 2, y, w / 2, h / 2), 2); DrawPane(e.Graphics, new RectangleF(x + w / 2, y + h / 2, w / 2, h / 2), 3); }
        else if (PaneCount == 3 && LayoutKey == "right-large")
        { DrawPane(e.Graphics, new RectangleF(x, y, w / 2, h / 2), 1); DrawPane(e.Graphics, new RectangleF(x, y + h / 2, w / 2, h / 2), 2); DrawPane(e.Graphics, new RectangleF(x + w / 2, y, w / 2, h), 3); }
        else if (PaneCount == 3)
            for (int i = 0; i < 3; i++) DrawPane(e.Graphics, new RectangleF(x + w * i / 3, y, w / 3, h), i + 1);
        else if (PaneCount == 4)
        {
            DrawPane(e.Graphics, new RectangleF(x, y, w / 2, h / 2), 1); DrawPane(e.Graphics, new RectangleF(x + w / 2, y, w / 2, h / 2), 2);
            DrawPane(e.Graphics, new RectangleF(x, y + h / 2, w / 2, h / 2), 3); DrawPane(e.Graphics, new RectangleF(x + w / 2, y + h / 2, w / 2, h / 2), 4);
        }
        else if (PaneCount == 5 && LayoutKey == "grid-3-2")
        { for (int i = 0; i < 3; i++) DrawPane(e.Graphics, new RectangleF(x + w * i / 3, y, w / 3, h / 2), i + 1); for (int i = 0; i < 2; i++) DrawPane(e.Graphics, new RectangleF(x + w * i / 2, y + h / 2, w / 2, h / 2), i + 4); }
        else if (PaneCount == 5)
        { for (int i = 0; i < 2; i++) DrawPane(e.Graphics, new RectangleF(x + w * i / 2, y, w / 2, h / 2), i + 1); for (int i = 0; i < 3; i++) DrawPane(e.Graphics, new RectangleF(x + w * i / 3, y + h / 2, w / 3, h / 2), i + 3); }
        else
            for (int row = 0; row < 2; row++) for (int col = 0; col < 3; col++) DrawPane(e.Graphics, new RectangleF(x + w * col / 3, y + h * row / 2, w / 3, h / 2), row * 3 + col + 1);
    }
}

internal sealed class MainForm : Form
{
    private const string WtInstallerResourceName = "PowerShellSplitWorkbench.WindowsTerminalInstaller.exe";
    private const string WtInstallerSha256 = "A78B8A22B3FDA382D74FD0575876C5A9E681D6E8D2866D0709BB43765C9F24A6";
    private const long LogRotationBytes = 500L * 1024L * 1024L;
    private readonly ComboBox count = new ComboBox(), layout = new ComboBox(), launchMode = new ComboBox(), profile = new ComboBox();
    private readonly LayoutPreview preview = new LayoutPreview();
    private readonly TableLayoutPanel dirTable = new TableLayoutPanel();
    private readonly List<TextBox> dirBoxes = new List<TextBox>();
    private readonly Dictionary<int, string> cache = new Dictionary<int, string>();
    private readonly ComboBox shell = new ComboBox();
    private readonly TextBox shellArguments = new TextBox();
    private readonly TextBox terminal = new TextBox();
    private readonly CheckBox closeAfter = new CheckBox();
    private readonly CheckBox rememberSettings = new CheckBox();
    private readonly CheckBox recordLogs = new CheckBox();
    private readonly ToolStripStatusLabel status = new ToolStripStatusLabel();
    private readonly ToolTip tips = new ToolTip();
    private readonly Button launchButton = new Button();
    private readonly bool persistenceEnabled;
    private int restoredMissingDirectoryCount;
    private bool launchInProgress;
    private bool preferredPowerShellLogging = true;
    private bool updatingLogAvailability;

    public MainForm() : this(true) { }

    internal MainForm(bool enablePersistence)
    {
        persistenceEnabled = enablePersistence;
        Text = "powershell 分屏工作台 V1.3.1 - Mangetic - 2026-9-11"; StartPosition = FormStartPosition.CenterScreen;
        try { Icon = Icon.ExtractAssociatedIcon(Assembly.GetExecutingAssembly().Location); } catch { }
        MinimumSize = new Size(920, 700); Size = new Size(1100, 840); Font = new Font("Microsoft YaHei UI", 9F);
        AutoScaleMode = AutoScaleMode.Dpi;
        BuildUi(); PopulateLayouts(); RebuildDirectories();
        if (persistenceEnabled) LoadSettings();
        RefreshProfiles(); UpdateLoggingAvailability();
    }

    private Label MakeLabel(string text) { return new Label { Text = text, AutoSize = true, Anchor = AnchorStyles.Left, Margin = new Padding(4, 8, 7, 4) }; }
    private int PaneCount { get { return count.SelectedItem == null ? 4 : (int)count.SelectedItem; } }
    private OptionItem SelectedLayout { get { return layout.SelectedItem as OptionItem; } }
    private string LaunchModeKey { get { OptionItem item = launchMode.SelectedItem as OptionItem; return item == null ? "standard" : item.Key; } }
    internal int DirectoryRowCount { get { return dirBoxes.Count; } }
    internal int LayoutOptionCount { get { return layout.Items.Count; } }
    internal int SelectedPaneCountForTest { get { return PaneCount; } }
    internal string SelectedLayoutForTest { get { return SelectedLayout == null ? "" : SelectedLayout.Key; } }
    internal string FirstDirectoryForTest { get { return dirBoxes.Count == 0 ? "" : dirBoxes[0].Text; } }
    internal string LaunchModeForTest { get { return LaunchModeKey; } }
    internal int ProfileCountForTest { get { return profile.Items.Count; } }
    internal bool RecordLogsForTest { get { return recordLogs.Checked; } }
    internal bool RecordLogsEnabledForTest { get { return recordLogs.Enabled; } }
    internal string RecordLogsTextForTest { get { return recordLogs.Text; } }
    internal string ShellArgumentsForTest { get { return shellArguments.Text; } }
    internal int LaunchModeOptionCountForTest { get { return launchMode.Items.Count; } }
    internal bool StrictLaunchStepsForTest()
    {
        string wt, windowTarget, logSession;
        bool previousLogs = recordLogs.Checked;
        try
        {
            recordLogs.Checked = false;
            List<List<string>> steps = BuildLaunchSteps(false, false, out wt, out windowTarget, out logSession);
            if (!windowTarget.StartsWith("PSSW-", StringComparison.Ordinal) || steps.Count != 5) return false;
            foreach (List<string> step in steps)
                if (step.Count < 2 || step[0] != "-w" || step[1] != windowTarget) return false;
            return true;
        }
        finally { recordLogs.Checked = previousLogs; }
    }
    internal bool FastLaunchOneShotForTest()
    {
        string wt, windowTarget, logSession;
        string previousMode = LaunchModeKey;
        bool previousLogs = recordLogs.Checked;
        try
        {
            SelectOption(launchMode, "fast");
            recordLogs.Checked = false;
            List<List<string>> steps = BuildLaunchSteps(false, false, out wt, out windowTarget, out logSession);
            if (steps.Count != 1 || !windowTarget.StartsWith("PSSW-", StringComparison.Ordinal)) return false;
            int splitCount = 0;
            foreach (string argument in steps[0]) if (argument == "split-pane") splitCount++;
            return splitCount == PaneCount - 1;
        }
        finally
        {
            SelectOption(launchMode, previousMode);
            recordLogs.Checked = previousLogs;
        }
    }
    internal bool LoggingPreviewForTest()
    {
        string wt, windowTarget, logSession;
        bool previousLogs = recordLogs.Checked;
        try
        {
            recordLogs.Checked = true;
            List<List<string>> steps = BuildLaunchSteps(false, false, out wt, out windowTarget, out logSession);
            if (String.IsNullOrWhiteSpace(logSession)) return false;
            if (logSession.IndexOfAny(Path.GetInvalidPathChars()) >= 0) return false;
            int transcriptCount = 0;
            foreach (List<string> step in steps)
            {
                string command = WtCommand.Join(step);
                transcriptCount += WtCommand.CountEncodedCommandsContaining(step, "Start-Transcript");
                if (command.IndexOf("<启动时间>", StringComparison.Ordinal) >= 0) return false;
            }
            return transcriptCount == PaneCount;
        }
        catch { return false; }
        finally { recordLogs.Checked = previousLogs; }
    }
    internal bool SettingsAlignmentForTest
    {
        get
        {
            Control countLabel = FindControlByText(this, "窗口数量");
            Control layoutLabel = FindControlByText(this, "布局");
            return IsVerticallyAligned(countLabel, count) && IsVerticallyAligned(layoutLabel, layout);
        }
    }
    private static Control FindControlByText(Control parent, string text)
    {
        foreach (Control child in parent.Controls)
        {
            if (child.Text == text) return child;
            Control found = FindControlByText(child, text); if (found != null) return found;
        }
        return null;
    }
    private static bool IsVerticallyAligned(Control label, Control field)
    {
        if (label == null || field == null || label.Parent != field.Parent) return false;
        int labelCenter = label.Top + label.Height / 2, fieldCenter = field.Top + field.Height / 2;
        return Math.Abs(labelCenter - fieldCenter) <= 8;
    }

    internal void SelectPaneCountForTest(int value)
    {
        count.SelectedItem = value;
        Application.DoEvents();
    }

    internal void SelectLaunchModeForTest(string mode)
    {
        SelectOption(launchMode, mode);
        Application.DoEvents();
    }

    internal void SelectShellForTest(string value)
    {
        shell.Text = value;
        Application.DoEvents();
    }

    internal void ConfigurePersistenceTest(string directory)
    {
        count.SelectedItem = 5;
        foreach (OptionItem item in layout.Items)
            if (item.Key == "grid-2-3") { layout.SelectedItem = item; break; }
        if (dirBoxes.Count > 0) dirBoxes[0].Text = directory;
        shell.Text = "powershell.exe";
        shellArguments.Text = "-WindowStyle Normal";
        SelectOption(launchMode, "standard");
        recordLogs.Checked = true;
        rememberSettings.Checked = true;
    }

    internal void ConfigureProfileTest(int paneCount, string mode, string directory, string shellValue, string argumentValue)
    {
        count.SelectedItem = paneCount;
        if (dirBoxes.Count > 0) dirBoxes[0].Text = directory;
        shell.Text = shellValue; shellArguments.Text = argumentValue; SelectOption(launchMode, mode);
        Application.DoEvents();
    }

    internal void SaveProfileForTest(string name) { profile.Text = name; SaveProfile(); }
    internal void LoadProfileForTest(string name) { profile.Text = name; LoadProfile(); }
    internal void DeleteProfileForTest(string name)
    {
        profile.Text = name; string path = FindSelectedProfile();
        if (path != null) File.Delete(path);
        profile.Text = ""; RefreshProfiles();
    }

    private void BuildUi()
    {
        TableLayoutPanel root = new TableLayoutPanel { Dock = DockStyle.Fill, Padding = new Padding(20, 16, 20, 10), ColumnCount = 1, RowCount = 8 };
        root.RowStyles.Add(new RowStyle(SizeType.AutoSize)); root.RowStyles.Add(new RowStyle(SizeType.AutoSize)); root.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        root.RowStyles.Add(new RowStyle(SizeType.AutoSize)); root.RowStyles.Add(new RowStyle(SizeType.Percent, 100)); root.RowStyles.Add(new RowStyle(SizeType.AutoSize)); root.RowStyles.Add(new RowStyle(SizeType.AutoSize)); root.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        Controls.Add(root);
        root.Controls.Add(new Label { Text = "powershell 分屏工作台", AutoSize = true, Font = new Font(Font.FontFamily, 18F, FontStyle.Bold) }, 0, 0);
        root.Controls.Add(new Label { Text = "选择窗口数量、布局和目录，然后一键打开 Windows Terminal。", AutoSize = true, ForeColor = Color.DimGray, Margin = new Padding(2, 0, 0, 12) }, 0, 1);

        GroupBox settings = new GroupBox { Text = "分屏设置", Dock = DockStyle.Top, AutoSize = true, Padding = new Padding(10), Margin = new Padding(0, 0, 0, 12) };
        TableLayoutPanel settingsHost = new TableLayoutPanel { Dock = DockStyle.Fill, AutoSize = true, ColumnCount = 2, RowCount = 1 };
        settingsHost.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100)); settingsHost.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 230));
        TableLayoutPanel settingsLeft = new TableLayoutPanel { Dock = DockStyle.Top, AutoSize = true, ColumnCount = 1, RowCount = 2 };
        settingsLeft.RowStyles.Add(new RowStyle(SizeType.AutoSize)); settingsLeft.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        FlowLayoutPanel primaryRow = new FlowLayoutPanel { Dock = DockStyle.Top, AutoSize = true, WrapContents = false, FlowDirection = FlowDirection.LeftToRight, Margin = new Padding(0) };
        FlowLayoutPanel modeRow = new FlowLayoutPanel { Dock = DockStyle.Top, AutoSize = true, WrapContents = false, FlowDirection = FlowDirection.LeftToRight, Margin = new Padding(0) };
        settingsLeft.Controls.Add(primaryRow, 0, 0); settingsLeft.Controls.Add(modeRow, 0, 1);
        settingsHost.Controls.Add(settingsLeft, 0, 0); settingsHost.Controls.Add(preview, 1, 0); settings.Controls.Add(settingsHost); root.Controls.Add(settings, 0, 3);
        count.DropDownStyle = ComboBoxStyle.DropDownList; count.Width = 75; count.Margin = new Padding(3, 5, 14, 5); for (int i = 2; i <= 6; i++) count.Items.Add(i); count.SelectedItem = 4;
        tips.SetToolTip(count, "选择要创建的终端 pane 数量（2–6）。");
        count.SelectedIndexChanged += delegate { PopulateLayouts(); RebuildDirectories(); };
        layout.DropDownStyle = ComboBoxStyle.DropDownList; layout.Width = 250; layout.Margin = new Padding(3, 5, 14, 5); layout.SelectedIndexChanged += delegate { RefreshPreview(); };
        tips.SetToolTip(layout, "布局预览中的编号与下方目录编号一致。");
        launchMode.DropDownStyle = ComboBoxStyle.DropDownList; launchMode.Width = 250; launchMode.Margin = new Padding(3, 5, 3, 5);
        launchMode.Items.Add(new OptionItem("fast", "快速（一次性提交）"));
        launchMode.Items.Add(new OptionItem("standard", "标准（推荐，V1.1 稳定流程）"));
        launchMode.SelectedIndex = 1;
        tips.SetToolTip(launchMode, "标准模式使用 V1.1 已验证的唯一窗口目标与 750/500 ms 分步节奏；快速模式一次提交完整布局。");
        preview.Dock = DockStyle.Fill; preview.Margin = new Padding(12, 2, 0, 2);
        primaryRow.Controls.Add(MakeLabel("窗口数量")); primaryRow.Controls.Add(count);
        primaryRow.Controls.Add(MakeLabel("布局")); primaryRow.Controls.Add(layout);
        modeRow.Controls.Add(MakeLabel("启动模式")); modeRow.Controls.Add(launchMode);

        GroupBox profiles = new GroupBox { Text = "工作区方案", Dock = DockStyle.Top, AutoSize = true, Padding = new Padding(10), Margin = new Padding(0, 0, 0, 12) };
        TableLayoutPanel pg = new TableLayoutPanel { Dock = DockStyle.Fill, AutoSize = true, ColumnCount = 6 };
        pg.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize)); pg.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        pg.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 100)); pg.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 100)); pg.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 100)); pg.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 10));
        profile.DropDownStyle = ComboBoxStyle.DropDown; profile.Dock = DockStyle.Fill;
        Button saveProfile = new Button { Text = "保存当前方案", Dock = DockStyle.Fill }; saveProfile.Click += delegate { SaveProfile(); };
        Button loadProfile = new Button { Text = "载入方案", Dock = DockStyle.Fill }; loadProfile.Click += delegate { LoadProfile(); };
        Button deleteProfile = new Button { Text = "删除方案", Dock = DockStyle.Fill }; deleteProfile.Click += delegate { DeleteProfile(); };
        tips.SetToolTip(profile, "输入方案名称后保存，或从下拉列表选择已有方案。");
        pg.Controls.Add(MakeLabel("方案名称"), 0, 0); pg.Controls.Add(profile, 1, 0); pg.Controls.Add(saveProfile, 2, 0); pg.Controls.Add(loadProfile, 3, 0); pg.Controls.Add(deleteProfile, 4, 0);
        profiles.Controls.Add(pg); root.Controls.Add(profiles, 0, 2);

        GroupBox dirs = new GroupBox { Text = "工作目录（按预览图编号；留空 = 所选终端默认目录）", Dock = DockStyle.Fill, Padding = new Padding(10), Margin = new Padding(0, 0, 0, 12) };
        TableLayoutPanel dirContainer = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 1, RowCount = 2 };
        dirContainer.RowStyles.Add(new RowStyle(SizeType.AutoSize)); dirContainer.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
        FlowLayoutPanel dirTools = new FlowLayoutPanel { Dock = DockStyle.Fill, AutoSize = true, FlowDirection = FlowDirection.RightToLeft, WrapContents = false, Margin = new Padding(0, 0, 0, 6) };
        Button clearAll = new Button { Text = "全部清空", AutoSize = true };
        clearAll.Click += delegate { foreach (TextBox box in dirBoxes) box.Clear(); };
        Button copyFirst = new Button { Text = "窗口 1 应用到全部", AutoSize = true };
        copyFirst.Click += delegate { CopyFirstDirectoryToAll(); };
        tips.SetToolTip(copyFirst, "将窗口 1 的目录复制到其他所有窗口。窗口 1 为空时会全部清空。");
        dirTools.Controls.Add(clearAll); dirTools.Controls.Add(copyFirst);
        Panel scroll = new Panel { Dock = DockStyle.Fill, AutoScroll = true }; dirTable.Dock = DockStyle.Top; dirTable.AutoSize = true; dirTable.ColumnCount = 4;
        dirTable.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 80)); dirTable.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100)); dirTable.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 100)); dirTable.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 65));
        scroll.Controls.Add(dirTable); dirContainer.Controls.Add(dirTools, 0, 0); dirContainer.Controls.Add(scroll, 0, 1); dirs.Controls.Add(dirContainer); root.Controls.Add(dirs, 0, 4);

        GroupBox advanced = new GroupBox { Text = "高级设置", Dock = DockStyle.Top, AutoSize = true, Padding = new Padding(10), Margin = new Padding(0, 0, 0, 12) };
        TableLayoutPanel ag = new TableLayoutPanel { Dock = DockStyle.Fill, AutoSize = true, ColumnCount = 6, RowCount = 4 };
        ag.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize)); ag.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 45)); ag.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 90)); ag.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize)); ag.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 55)); ag.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 80));
        advanced.Controls.Add(ag); root.Controls.Add(advanced, 0, 5);
        shell.DropDownStyle = ComboBoxStyle.DropDown; shell.Dock = DockStyle.Fill; PopulateShellChoices(); shell.Text = "powershell.exe"; terminal.Dock = DockStyle.Fill;
        shell.TextChanged += delegate { UpdateLoggingAvailability(); };
        shellArguments.Dock = DockStyle.Fill;
        tips.SetToolTip(shell, "选择终端程序或填写完整路径。填写 Python 安装目录（如 D:\\Python310）时会自动使用其中的 python.exe。");
        tips.SetToolTip(shellArguments, "终端打开后自动执行一次。PowerShell/CMD 填 dir，Python 填 print('hello')，Git Bash 填 ls。其他程序按参数处理，例如 ADB 填 -s DEVICE_SERIAL shell。");
        tips.SetToolTip(terminal, "留空时自动查找 Windows Terminal；自动查找失败时再手动指定 wt.exe。");
        Button chooseShell = new Button { Text = "选择程序…", Dock = DockStyle.Fill }; chooseShell.Click += delegate { ChooseShell(); };
        Button chooseWt = new Button { Text = "选择…", Dock = DockStyle.Fill }; chooseWt.Click += delegate { ChooseTerminal(); };
        closeAfter.Text = "启动后关闭本窗口"; closeAfter.AutoSize = true; closeAfter.Anchor = AnchorStyles.Left;
        rememberSettings.Text = "记住上次设置"; rememberSettings.AutoSize = true; rememberSettings.Anchor = AnchorStyles.Left; rememberSettings.Checked = true;
        recordLogs.Text = "记录每个窗口的运行输出"; recordLogs.AutoSize = true; recordLogs.Anchor = AnchorStyles.Left; recordLogs.Checked = true;
        recordLogs.CheckedChanged += delegate { if (!updatingLogAvailability && recordLogs.Enabled) preferredPowerShellLogging = recordLogs.Checked; };
        tips.SetToolTip(rememberSettings, "保存窗口数量、布局、目录和高级设置，下次打开时自动恢复。");
        tips.SetToolTip(recordLogs, "PowerShell 使用原生 Transcript 记录每个 pane。Python、Git Bash、CMD、ADB 等为保证交互和布局稳定，将直接启动并跳过日志代理。");
        Button openLogs = new Button { Text = "打开日志目录", AutoSize = true, Anchor = AnchorStyles.Left }; openLogs.Click += delegate { OpenLogDirectory(); };
        Button cleanupProcesses = new Button { Text = "清理本工具进程", AutoSize = true, Anchor = AnchorStyles.Left }; cleanupProcesses.Click += delegate { CleanupManagedProcesses(); };
        Button installWt = new Button { Text = "安装 WT", AutoSize = true, Anchor = AnchorStyles.Left }; installWt.Click += delegate { InstallWindowsTerminal(); };
        FlowLayoutPanel logActions = new FlowLayoutPanel { AutoSize = true, Dock = DockStyle.Fill, WrapContents = false, FlowDirection = FlowDirection.LeftToRight, Margin = new Padding(0) };
        logActions.Controls.Add(openLogs); logActions.Controls.Add(cleanupProcesses); logActions.Controls.Add(installWt);
        tips.SetToolTip(cleanupProcesses, "查找并清理本工具日志转发器及其子终端。操作前会显示数量并要求确认，不会结束普通 PowerShell。");
        tips.SetToolTip(installWt, "将主程序内置的微软 Windows Terminal 安装器释放到本地，校验完整性后可立即运行。");
        ag.Controls.Add(MakeLabel("终端程序"), 0, 0); ag.Controls.Add(shell, 1, 0); ag.Controls.Add(chooseShell, 2, 0);
        ag.Controls.Add(MakeLabel("wt.exe"), 3, 0); ag.Controls.Add(terminal, 4, 0); ag.Controls.Add(chooseWt, 5, 0);
        ag.Controls.Add(MakeLabel("启动后执行命令"), 0, 1); ag.Controls.Add(shellArguments, 1, 1); ag.SetColumnSpan(shellArguments, 5);
        ag.Controls.Add(rememberSettings, 0, 2); ag.SetColumnSpan(rememberSettings, 3);
        ag.Controls.Add(closeAfter, 3, 2); ag.SetColumnSpan(closeAfter, 3);
        ag.Controls.Add(recordLogs, 0, 3); ag.SetColumnSpan(recordLogs, 3);
        ag.Controls.Add(logActions, 3, 3); ag.SetColumnSpan(logActions, 3);

        FlowLayoutPanel buttons = new FlowLayoutPanel { Dock = DockStyle.Fill, AutoSize = true, FlowDirection = FlowDirection.RightToLeft, WrapContents = false, Margin = new Padding(0, 0, 0, 8) };
        launchButton.Text = "启动分屏"; launchButton.Width = 120; launchButton.Height = 34; launchButton.Click += delegate { Launch(); };
        Button show = new Button { Text = "预览命令", Width = 110, Height = 34 }; show.Click += delegate { ShowCommand(); };
        buttons.Controls.Add(launchButton); buttons.Controls.Add(show); root.Controls.Add(buttons, 0, 6);
        AcceptButton = launchButton;
        StatusStrip strip = new StatusStrip { SizingGrip = false }; status.Text = "准备就绪。启动后可用 Alt+Shift+方向键调整 pane 大小。"; status.Spring = true; status.TextAlign = ContentAlignment.MiddleLeft;
        strip.Items.Add(status); root.Controls.Add(strip, 0, 7);
    }

    protected override void OnShown(EventArgs e)
    {
        base.OnShown(e);
        try { Directory.CreateDirectory(LogRootDirectory); }
        catch (Exception ex) { recordLogs.Checked = false; status.Text = "无法创建日志目录：" + ex.Message; }
        string wt = FindTerminal();
        if (restoredMissingDirectoryCount > 0)
            status.Text = "已恢复设置，但有 " + restoredMissingDirectoryCount + " 个目录当前不存在；启动前请检查。";
        else
            status.Text = wt == null
                ? "未检测到 Windows Terminal；请在高级设置中选择 wt.exe。"
                : "已检测到 Windows Terminal。启动后用 Alt+Shift+方向键调整 pane 大小。";
    }

    protected override void OnFormClosing(FormClosingEventArgs e)
    {
        if (launchInProgress) { e.Cancel = true; status.Text = "布局正在创建，请稍候完成后再关闭。"; return; }
        if (persistenceEnabled) SaveSettings();
        base.OnFormClosing(e);
    }

    private static string SettingsPath
    {
        get
        {
            string overridePath = Environment.GetEnvironmentVariable("PSSW_SETTINGS_PATH");
            if (!String.IsNullOrWhiteSpace(overridePath)) return overridePath;
            return Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                "PowerShellSplitWorkbench",
                "settings.ini");
        }
    }

    private static string ProfilesDirectory
    {
        get
        {
            string overridePath = Environment.GetEnvironmentVariable("PSSW_PROFILES_PATH");
            if (!String.IsNullOrWhiteSpace(overridePath)) return overridePath;
            return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "PowerShellSplitWorkbench", "profiles");
        }
    }

    private static string LogRootDirectory
    {
        get { return Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "窗口运行日志"); }
    }

    private static string EncodeSetting(string value)
    {
        return Convert.ToBase64String(Encoding.UTF8.GetBytes(value ?? ""));
    }

    private static string DecodeSetting(string value)
    {
        try { return Encoding.UTF8.GetString(Convert.FromBase64String(value ?? "")); }
        catch { return ""; }
    }

    private void LoadSettings()
    {
        try
        {
            if (!File.Exists(SettingsPath)) return;
            Dictionary<string, string> values = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
            foreach (string line in File.ReadAllLines(SettingsPath, Encoding.UTF8))
            {
                int separator = line.IndexOf('=');
                if (separator > 0) values[line.Substring(0, separator)] = line.Substring(separator + 1);
            }
            string raw;
            if (values.TryGetValue("remember", out raw) && raw == "0")
            {
                rememberSettings.Checked = false;
                return;
            }
            rememberSettings.Checked = true;

            int savedCount;
            if (values.TryGetValue("count", out raw) && Int32.TryParse(raw, out savedCount) && savedCount >= 2 && savedCount <= 6)
                count.SelectedItem = savedCount;

            if (values.TryGetValue("layout", out raw))
                foreach (OptionItem item in layout.Items)
                    if (item.Key == raw) { layout.SelectedItem = item; break; }

            if (values.TryGetValue("launchMode", out raw)) SelectOption(launchMode, raw == "stable" ? "standard" : raw);

            if (values.TryGetValue("shell", out raw)) shell.Text = DecodeSetting(raw);
            if (values.TryGetValue("shellArguments", out raw)) shellArguments.Text = DecodeSetting(raw);
            if (values.TryGetValue("terminal", out raw)) terminal.Text = DecodeSetting(raw);
            if (values.TryGetValue("closeAfter", out raw)) closeAfter.Checked = raw == "1";
            if (values.TryGetValue("recordLogs", out raw)) preferredPowerShellLogging = raw != "0";

            restoredMissingDirectoryCount = 0;
            for (int i = 0; i < dirBoxes.Count; i++)
            {
                if (!values.TryGetValue("dir" + i, out raw)) continue;
                string path = DecodeSetting(raw);
                dirBoxes[i].Text = path;
                if (path.Length > 0 && !Directory.Exists(path)) restoredMissingDirectoryCount++;
            }
        }
        catch
        {
            status.Text = "上次设置读取失败，已使用默认设置。";
        }
    }

    private void SaveSettings()
    {
        try
        {
            string directory = Path.GetDirectoryName(SettingsPath);
            Directory.CreateDirectory(directory);
            if (!rememberSettings.Checked)
            {
                File.WriteAllText(SettingsPath, "remember=0" + Environment.NewLine, Encoding.UTF8);
                return;
            }
            List<string> lines = new List<string>();
            lines.Add("version=3");
            lines.Add("remember=1");
            lines.Add("count=" + PaneCount);
            lines.Add("layout=" + (SelectedLayout == null ? "" : SelectedLayout.Key));
            lines.Add("launchMode=" + LaunchModeKey);
            lines.Add("shell=" + EncodeSetting(shell.Text));
            lines.Add("shellArguments=" + EncodeSetting(shellArguments.Text));
            lines.Add("terminal=" + EncodeSetting(terminal.Text));
            lines.Add("closeAfter=" + (closeAfter.Checked ? "1" : "0"));
            lines.Add("recordLogs=" + (preferredPowerShellLogging ? "1" : "0"));
            for (int i = 0; i < dirBoxes.Count; i++) lines.Add("dir" + i + "=" + EncodeSetting(dirBoxes[i].Text));
            File.WriteAllLines(SettingsPath, lines.ToArray(), Encoding.UTF8);
        }
        catch
        {
            // Closing the application must never be blocked by a settings error.
        }
    }

    private void PopulateLayouts()
    {
        layout.Items.Clear(); foreach (OptionItem item in WtCommand.Layouts[PaneCount]) layout.Items.Add(item); layout.SelectedIndex = 0; RefreshPreview();
    }
    private static void SelectOption(ComboBox box, string key)
    {
        foreach (object value in box.Items)
        {
            OptionItem item = value as OptionItem;
            if (item != null && item.Key == key) { box.SelectedItem = item; return; }
        }
    }
    private void UpdateLoggingAvailability()
    {
        string resolved = FindExe(shell.Text) ?? shell.Text.Trim();
        string name = Path.GetFileName(resolved).ToLowerInvariant();
        bool supported = name == "powershell.exe" || name == "pwsh.exe";
        updatingLogAvailability = true;
        try
        {
            recordLogs.Enabled = supported;
            recordLogs.Checked = supported && preferredPowerShellLogging;
            recordLogs.Text = supported ? "记录每个窗口的运行输出" : "运行日志（当前终端不支持）";
            tips.SetToolTip(recordLogs, supported
                ? "PowerShell 使用原生 Transcript 记录每个 pane。"
                : "为保证交互和分屏稳定，Python、Git Bash、CMD、ADB、WSL 等终端暂不启用运行日志。");
        }
        finally { updatingLogAvailability = false; }
    }

    private static Dictionary<string, string> ReadValues(string path)
    {
        Dictionary<string, string> values = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        foreach (string line in File.ReadAllLines(path, Encoding.UTF8))
        {
            int separator = line.IndexOf('=');
            if (separator > 0) values[line.Substring(0, separator)] = line.Substring(separator + 1);
        }
        return values;
    }
    private string ProfileName(string path)
    {
        try { string raw; Dictionary<string, string> values = ReadValues(path); return values.TryGetValue("name", out raw) ? DecodeSetting(raw) : Path.GetFileNameWithoutExtension(path); }
        catch { return Path.GetFileNameWithoutExtension(path); }
    }
    private void RefreshProfiles()
    {
        string current = profile.Text; profile.Items.Clear();
        if (Directory.Exists(ProfilesDirectory))
            foreach (string path in Directory.GetFiles(ProfilesDirectory, "*.ini")) profile.Items.Add(new OptionItem(path, ProfileName(path)));
        profile.Text = current;
    }
    private string FindSelectedProfile()
    {
        OptionItem selected = profile.SelectedItem as OptionItem;
        if (selected != null && File.Exists(selected.Key)) return selected.Key;
        if (!Directory.Exists(ProfilesDirectory)) return null;
        foreach (string path in Directory.GetFiles(ProfilesDirectory, "*.ini"))
            if (String.Equals(ProfileName(path), profile.Text.Trim(), StringComparison.OrdinalIgnoreCase)) return path;
        return null;
    }
    private List<string> CurrentProfileLines(string name)
    {
        List<string> lines = new List<string>();
        lines.Add("version=3"); lines.Add("name=" + EncodeSetting(name)); lines.Add("count=" + PaneCount);
        lines.Add("layout=" + (SelectedLayout == null ? "" : SelectedLayout.Key));
        lines.Add("launchMode=" + LaunchModeKey); lines.Add("shell=" + EncodeSetting(shell.Text)); lines.Add("shellArguments=" + EncodeSetting(shellArguments.Text)); lines.Add("terminal=" + EncodeSetting(terminal.Text));
        lines.Add("closeAfter=" + (closeAfter.Checked ? "1" : "0"));
        lines.Add("recordLogs=" + (preferredPowerShellLogging ? "1" : "0"));
        for (int i = 0; i < dirBoxes.Count; i++) lines.Add("dir" + i + "=" + EncodeSetting(dirBoxes[i].Text));
        return lines;
    }
    private void SaveProfile()
    {
        try
        {
            string name = profile.Text.Trim(); if (name.Length == 0) throw new InvalidOperationException("请先输入方案名称。");
            Directory.CreateDirectory(ProfilesDirectory); string path = FindSelectedProfile();
            if (path == null) path = Path.Combine(ProfilesDirectory, Guid.NewGuid().ToString("N") + ".ini");
            File.WriteAllLines(path, CurrentProfileLines(name).ToArray(), Encoding.UTF8); RefreshProfiles();
            foreach (OptionItem item in profile.Items) if (item.Text == name) { profile.SelectedItem = item; break; }
            status.Text = "工作区方案“" + name + "”已保存。";
        }
        catch (Exception ex) { MessageBox.Show(this, ex.Message, "保存方案失败", MessageBoxButtons.OK, MessageBoxIcon.Warning); }
    }
    private void ApplyProfile(Dictionary<string, string> values)
    {
        string raw; int savedCount;
        if (values.TryGetValue("count", out raw) && Int32.TryParse(raw, out savedCount) && savedCount >= 2 && savedCount <= 6) count.SelectedItem = savedCount;
        if (values.TryGetValue("layout", out raw)) SelectOption(layout, raw);
        if (values.TryGetValue("launchMode", out raw)) SelectOption(launchMode, raw == "stable" ? "standard" : raw);
        if (values.TryGetValue("shell", out raw)) shell.Text = DecodeSetting(raw);
        if (values.TryGetValue("shellArguments", out raw)) shellArguments.Text = DecodeSetting(raw);
        if (values.TryGetValue("terminal", out raw)) terminal.Text = DecodeSetting(raw);
        if (values.TryGetValue("closeAfter", out raw)) closeAfter.Checked = raw == "1";
        if (values.TryGetValue("recordLogs", out raw)) preferredPowerShellLogging = raw != "0";
        for (int i = 0; i < dirBoxes.Count; i++) if (values.TryGetValue("dir" + i, out raw)) dirBoxes[i].Text = DecodeSetting(raw);
        UpdateLoggingAvailability();
    }
    private void LoadProfile()
    {
        try
        {
            string path = FindSelectedProfile(); if (path == null) throw new InvalidOperationException("请选择一个已有方案。");
            string name = ProfileName(path); ApplyProfile(ReadValues(path)); profile.Text = name; status.Text = "工作区方案“" + name + "”已载入。";
        }
        catch (Exception ex) { MessageBox.Show(this, ex.Message, "载入方案失败", MessageBoxButtons.OK, MessageBoxIcon.Warning); }
    }
    private void DeleteProfile()
    {
        try
        {
            string path = FindSelectedProfile(); if (path == null) throw new InvalidOperationException("请选择一个已有方案。");
            string name = ProfileName(path);
            if (MessageBox.Show(this, "确定删除工作区方案“" + name + "”吗？", "删除方案", MessageBoxButtons.YesNo, MessageBoxIcon.Question) != DialogResult.Yes) return;
            File.Delete(path); profile.Text = ""; RefreshProfiles(); status.Text = "工作区方案已删除。";
        }
        catch (Exception ex) { MessageBox.Show(this, ex.Message, "删除方案失败", MessageBoxButtons.OK, MessageBoxIcon.Warning); }
    }
    private void OpenLogDirectory()
    {
        try
        {
            Directory.CreateDirectory(LogRootDirectory);
            Process.Start(new ProcessStartInfo { FileName = "explorer.exe", Arguments = WtCommand.Quote(LogRootDirectory), UseShellExecute = false });
        }
        catch (Exception ex) { MessageBox.Show(this, ex.Message, "打开日志目录失败", MessageBoxButtons.OK, MessageBoxIcon.Warning); }
    }
    private static string Sha256Of(string path)
    {
        using (SHA256 sha = SHA256.Create())
        using (FileStream input = File.OpenRead(path))
        {
            byte[] hash = sha.ComputeHash(input);
            StringBuilder text = new StringBuilder(hash.Length * 2);
            foreach (byte value in hash) text.Append(value.ToString("X2"));
            return text.ToString();
        }
    }
    internal static bool EmbeddedWindowsTerminalInstallerIsValidForTest()
    {
        try
        {
            using (Stream resource = Assembly.GetExecutingAssembly().GetManifestResourceStream(WtInstallerResourceName))
            {
                if (resource == null || resource.Length != 815136) return false;
                using (SHA256 sha = SHA256.Create())
                {
                    byte[] hash = sha.ComputeHash(resource);
                    StringBuilder text = new StringBuilder(hash.Length * 2);
                    foreach (byte value in hash) text.Append(value.ToString("X2"));
                    return String.Equals(text.ToString(), WtInstallerSha256, StringComparison.OrdinalIgnoreCase);
                }
            }
        }
        catch { return false; }
    }
    private static string ExtractWindowsTerminalInstallerTo(string directory)
    {
        Directory.CreateDirectory(directory);
        string destination = Path.Combine(directory, "Windows Terminal Installer.exe");
        if (File.Exists(destination) && String.Equals(Sha256Of(destination), WtInstallerSha256, StringComparison.OrdinalIgnoreCase))
            return destination;

        string temporary = destination + ".tmp-" + Guid.NewGuid().ToString("N");
        try
        {
            using (Stream resource = Assembly.GetExecutingAssembly().GetManifestResourceStream(WtInstallerResourceName))
            {
                if (resource == null) throw new InvalidOperationException("主程序中没有找到内置的 Windows Terminal 安装器资源，请重新编译或重新下载本工具。");
                using (FileStream output = new FileStream(temporary, FileMode.CreateNew, FileAccess.Write, FileShare.None)) resource.CopyTo(output);
            }
            if (!String.Equals(Sha256Of(temporary), WtInstallerSha256, StringComparison.OrdinalIgnoreCase))
                throw new InvalidDataException("内置 Windows Terminal 安装器的 SHA-256 校验失败，已停止运行。");
            if (File.Exists(destination)) File.Delete(destination);
            File.Move(temporary, destination);
            return destination;
        }
        finally { try { if (File.Exists(temporary)) File.Delete(temporary); } catch { } }
    }
    private static string ExtractWindowsTerminalInstaller()
    {
        return ExtractWindowsTerminalInstallerTo(Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "PowerShellSplitWorkbench", "安装程序"));
    }
    internal static bool ExtractWindowsTerminalInstallerForTest(string directory)
    {
        try
        {
            string path = ExtractWindowsTerminalInstallerTo(directory);
            return File.Exists(path) && new FileInfo(path).Length == 815136 &&
                String.Equals(Sha256Of(path), WtInstallerSha256, StringComparison.OrdinalIgnoreCase);
        }
        catch { return false; }
    }
    private void InstallWindowsTerminal()
    {
        try
        {
            string installer = ExtractWindowsTerminalInstaller();
            status.Text = "Windows Terminal 安装器已释放到：" + installer;
            string message = "安装器已保存到本地：\n" + installer +
                "\n\nSHA-256 校验通过：\n" + WtInstallerSha256 +
                "\n\n该文件具有有效的 Microsoft 数字签名。是否现在运行安装程序？";
            if (MessageBox.Show(this, message, "安装 Windows Terminal", MessageBoxButtons.YesNo, MessageBoxIcon.Question) != DialogResult.Yes) return;
            Process.Start(new ProcessStartInfo { FileName = installer, UseShellExecute = true });
            status.Text = "已启动 Windows Terminal 安装程序。";
        }
        catch (Exception ex) { MessageBox.Show(this, ex.Message, "安装 WT 失败", MessageBoxButtons.OK, MessageBoxIcon.Error); }
    }
    private sealed class CleanupTargets
    {
        public readonly List<Process> LoggerGroups = new List<Process>();
        public readonly List<Process> OrphanShellGroups = new List<Process>();
        public IEnumerable<Process> All
        {
            get { foreach (Process process in LoggerGroups) yield return process; foreach (Process process in OrphanShellGroups) yield return process; }
        }
    }
    private static CleanupTargets ManagedProcesses()
    {
        CleanupTargets result = new CleanupTargets();
        string directory = Path.GetFullPath(AppDomain.CurrentDomain.BaseDirectory).TrimEnd(Path.DirectorySeparatorChar);
        foreach (Process process in Process.GetProcesses())
        {
            try
            {
                if (process.Id == Process.GetCurrentProcess().Id || process.MainWindowHandle != IntPtr.Zero) { process.Dispose(); continue; }
                string path = process.MainModule.FileName;
                string name = Path.GetFileName(path);
                string processDirectory = Path.GetFullPath(Path.GetDirectoryName(path)).TrimEnd(Path.DirectorySeparatorChar);
                bool sameDirectory = String.Equals(directory, processDirectory, StringComparison.OrdinalIgnoreCase);
                bool workbenchImage = name.StartsWith("powershell 分屏工作台 V1.", StringComparison.OrdinalIgnoreCase) && name.EndsWith(".exe", StringComparison.OrdinalIgnoreCase);
                // A logger always has a child shell. Requiring a descendant
                // prevents a just-started or hidden GUI instance being selected.
                if (sameDirectory && workbenchImage && ProcessTree.Descendants(process.Id).Count > 0) result.LoggerGroups.Add(process);
                else if (IsOrphanShellGroup(process)) result.OrphanShellGroups.Add(process);
                else process.Dispose();
            }
            catch { process.Dispose(); }
        }
        return result;
    }
    private static bool IsOrphanShellGroup(Process process)
    {
        try
        {
            string name = process.ProcessName;
            if (!String.Equals(name, "powershell", StringComparison.OrdinalIgnoreCase) || process.MainWindowHandle != IntPtr.Zero) return false;
            if (ProcessTree.ParentIsAlive(process.Id)) return false;
            List<int> descendants = ProcessTree.Descendants(process.Id);
            if (descendants.Count == 0) return false;
            // Old pre-logger builds started PowerShell directly with exactly
            // these persistence switches. Requiring an orphan parent, no GUI,
            // and a live child avoids matching an ordinary user shell.
            string commandLine = ProcessCommandLine.Read(process.Id);
            return commandLine.IndexOf("-NoLogo", StringComparison.OrdinalIgnoreCase) >= 0 &&
                commandLine.IndexOf("-NoExit", StringComparison.OrdinalIgnoreCase) >= 0;
        }
        catch { return false; }
    }
    private void CleanupManagedProcesses()
    {
        CleanupTargets targets = ManagedProcesses();
        List<Process> processes = new List<Process>(targets.All);
        try
        {
            if (processes.Count == 0)
            {
                MessageBox.Show(this, "没有检测到本工具遗留的日志转发进程或孤立终端进程。", "清理本工具进程", MessageBoxButtons.OK, MessageBoxIcon.Information);
                return;
            }
            string message = "检测结果：\n" +
                "• 日志转发进程组：" + targets.LoggerGroups.Count + "\n" +
                "• 旧版孤立 PowerShell 进程组：" + targets.OrphanShellGroups.Count + "\n\n" +
                "继续会关闭这些进程及其 PowerShell、CMD、Git Bash、ADB 或 Ping 子进程。\n" +
                "父进程仍存在的 Windows Terminal PowerShell 不会被匹配。确定继续吗？";
            if (MessageBox.Show(this, message, "确认清理本工具进程", MessageBoxButtons.YesNo, MessageBoxIcon.Warning) != DialogResult.Yes) return;
            int cleaned = 0, failed = 0;
            foreach (Process process in processes)
            {
                try { if (ProcessTree.KillTree(process.Id)) cleaned++; else failed++; }
                catch { failed++; }
            }
            status.Text = "清理完成：成功 " + cleaned + " 个，失败 " + failed + " 个进程组。";
            MessageBox.Show(this, "清理结果：\n• 成功：" + cleaned + " 个进程组\n• 失败：" + failed + " 个进程组" +
                (failed > 0 ? "\n\n失败项仍在运行，可能需要管理员权限或手动结束。" : ""),
                failed > 0 ? "清理未完全完成" : "清理完成", MessageBoxButtons.OK,
                failed > 0 ? MessageBoxIcon.Warning : MessageBoxIcon.Information);
        }
        finally { foreach (Process process in processes) process.Dispose(); }
    }
    internal static string CleanupScanReport()
    {
        CleanupTargets targets = ManagedProcesses();
        try
        {
            StringBuilder report = new StringBuilder();
            report.AppendLine("日志转发进程组=" + targets.LoggerGroups.Count);
            report.AppendLine("孤立终端进程组=" + targets.OrphanShellGroups.Count);
            foreach (Process process in targets.LoggerGroups) report.AppendLine("日志组PID=" + process.Id);
            foreach (Process process in targets.OrphanShellGroups) report.AppendLine("孤立组PID=" + process.Id);
            return report.ToString();
        }
        finally { foreach (Process process in targets.All) process.Dispose(); }
    }
    private void RefreshPreview() { preview.PaneCount = PaneCount; preview.LayoutKey = SelectedLayout == null ? "grid" : SelectedLayout.Key; preview.Invalidate(); }

    private void RebuildDirectories()
    {
        for (int i = 0; i < dirBoxes.Count; i++) cache[i] = dirBoxes[i].Text;
        dirBoxes.Clear(); dirTable.SuspendLayout(); dirTable.Controls.Clear(); dirTable.RowStyles.Clear(); dirTable.RowCount = PaneCount;
        for (int i = 0; i < PaneCount; i++)
        {
            dirTable.RowStyles.Add(new RowStyle(SizeType.AutoSize)); TextBox box = new TextBox { Dock = DockStyle.Fill, Margin = new Padding(3, 6, 8, 6) };
            string old; if (cache.TryGetValue(i, out old)) box.Text = old; dirBoxes.Add(box);
            Button choose = new Button { Text = "选择目录…", Dock = DockStyle.Fill, Margin = new Padding(0, 3, 6, 3), Tag = box };
            choose.Click += delegate(object sender, EventArgs e) { ChooseDirectory((TextBox)((Button)sender).Tag); };
            Button clear = new Button { Text = "清空", Dock = DockStyle.Fill, Margin = new Padding(0, 3, 0, 3), Tag = box };
            clear.Click += delegate(object sender, EventArgs e) { ((TextBox)((Button)sender).Tag).Clear(); };
            dirTable.Controls.Add(MakeLabel("窗口 " + (i + 1)), 0, i); dirTable.Controls.Add(box, 1, i); dirTable.Controls.Add(choose, 2, i); dirTable.Controls.Add(clear, 3, i);
        }
        dirTable.ResumeLayout(true);
    }

    private void CopyFirstDirectoryToAll()
    {
        if (dirBoxes.Count == 0) return;
        string value = dirBoxes[0].Text;
        for (int i = 1; i < dirBoxes.Count; i++) dirBoxes[i].Text = value;
    }

    private void ChooseDirectory(TextBox box)
    {
        using (FolderBrowserDialog d = new FolderBrowserDialog()) { d.Description = "选择该窗口的工作目录"; if (Directory.Exists(box.Text)) d.SelectedPath = box.Text; if (d.ShowDialog(this) == DialogResult.OK) box.Text = d.SelectedPath; }
    }
    private void ChooseTerminal()
    {
        using (OpenFileDialog d = new OpenFileDialog()) { d.Title = "选择 Windows Terminal"; d.Filter = "Windows Terminal (wt.exe)|wt.exe|可执行文件 (*.exe)|*.exe"; if (d.ShowDialog(this) == DialogResult.OK) terminal.Text = d.FileName; }
    }
    private void ChooseShell()
    {
        using (OpenFileDialog d = new OpenFileDialog())
        {
            d.Title = "选择要在每个窗口中运行的控制台程序";
            d.Filter = "可执行文件 (*.exe;*.com;*.bat;*.cmd)|*.exe;*.com;*.bat;*.cmd|所有文件 (*.*)|*.*";
            string current = FindExe(shell.Text);
            if (current != null) { d.InitialDirectory = Path.GetDirectoryName(current); d.FileName = Path.GetFileName(current); }
            if (d.ShowDialog(this) == DialogResult.OK) shell.Text = d.FileName;
        }
    }

    private static string FindExe(string value)
    {
        if (String.IsNullOrWhiteSpace(value)) return null; value = Environment.ExpandEnvironmentVariables(value.Trim().Trim('"'));
        if (File.Exists(value)) return Path.GetFullPath(value);
        if (Directory.Exists(value))
        {
            try
            {
                string[] preferred = { "python.exe", "python3.exe", "pwsh.exe", "powershell.exe", "cmd.exe", "bash.exe", "adb.exe" };
                foreach (string name in preferred)
                {
                    string candidate = Path.Combine(value, name);
                    if (File.Exists(candidate)) return Path.GetFullPath(candidate);
                }
                string[] executables = Directory.GetFiles(value, "*.exe", SearchOption.TopDirectoryOnly);
                if (executables.Length == 1) return Path.GetFullPath(executables[0]);
            }
            catch { }
            return null;
        }
        if (value.Contains("\\") || value.Contains("/")) return null;
        foreach (string raw in (Environment.GetEnvironmentVariable("PATH") ?? "").Split(Path.PathSeparator))
        { try { string file = Path.Combine(raw.Trim().Trim('"'), value); if (File.Exists(file)) return file; } catch { } }
        return null;
    }
    internal static string FindExeForTest(string value) { return FindExe(value); }
    private static string FindGitBash()
    {
        string git = FindExe("git.exe");
        if (git != null)
        {
            try
            {
                string root = Directory.GetParent(Path.GetDirectoryName(git)).FullName;
                string bash = Path.Combine(root, "bin", "bash.exe");
                if (File.Exists(bash)) return bash;
            }
            catch { }
        }
        string pf = Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles);
        string pf86 = Environment.GetFolderPath(Environment.SpecialFolder.ProgramFilesX86);
        string local = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
        string[] candidates = {
            Path.Combine(pf, "Git", "bin", "bash.exe"),
            Path.Combine(pf86, "Git", "bin", "bash.exe"),
            Path.Combine(local, "Programs", "Git", "bin", "bash.exe")
        };
        foreach (string candidate in candidates) if (File.Exists(candidate)) return candidate;
        return null;
    }
    private void PopulateShellChoices()
    {
        shell.Items.Clear();
        shell.Items.Add("powershell.exe");
        shell.Items.Add("pwsh.exe");
        shell.Items.Add("cmd.exe");
        shell.Items.Add("wsl.exe");
        string gitBash = FindGitBash();
        if (gitBash != null) shell.Items.Add(gitBash);
    }
    private string FindTerminal()
    {
        if (terminal.Text.Trim().Length > 0) return FindExe(terminal.Text); string found = FindExe("wt.exe"); if (found != null) return found;
        string local = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), pf = Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles);
        string[] paths = { Path.Combine(local, "Microsoft", "WindowsApps", "wt.exe"), Path.Combine(local, "Microsoft", "Windows Terminal", "wt.exe"), Path.Combine(pf, "Windows Terminal", "wt.exe") };
        foreach (string path in paths)
        {
            try
            {
                if (File.Exists(path)) return path;
                // Store application execution aliases can be launchable even
                // when querying their metadata is denied. Keep the standard
                // alias as a fallback and let Process.Start perform the final
                // validation when its parent directory is present.
                if (path.EndsWith(Path.Combine("WindowsApps", "wt.exe"), StringComparison.OrdinalIgnoreCase) && Directory.Exists(Path.GetDirectoryName(path))) return path;
            }
            catch { }
        }
        return null;
    }
    private static void RunTerminalStep(string wt, IList<string> step, int stepNumber, int timeoutMilliseconds = 7000, bool terminateOnTimeout = false)
    {
        using (Process process = Process.Start(new ProcessStartInfo { FileName = wt, Arguments = WtCommand.Join(step), UseShellExecute = false, WorkingDirectory = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), CreateNoWindow = true }))
        {
            if (process == null) throw new InvalidOperationException("Windows Terminal 步骤 " + stepNumber + " 未能启动。");
            if (!process.WaitForExit(timeoutMilliseconds))
            {
                // A timed-out wt.exe may already own a visible Terminal window.
                // Do not close user-visible terminals just because the launcher
                // did not exit in time. Only controlled self-tests opt in to
                // terminating their deliberately delayed helper process.
                if (terminateOnTimeout) try { process.Kill(); process.WaitForExit(3000); } catch { }
                throw new TimeoutException("Windows Terminal 步骤 " + stepNumber + " 在 " + (timeoutMilliseconds / 1000.0).ToString("0.###") + " 秒内没有完成。已停止后续分屏命令，请稍后重试。");
            }
            if (process.ExitCode != 0) throw new InvalidOperationException("Windows Terminal 步骤 " + stepNumber + " 执行失败，退出码：" + process.ExitCode);
        }
    }
    internal static bool TerminalTimeoutForTest()
    {
        try
        {
            RunTerminalStep(Assembly.GetExecutingAssembly().Location, new string[] { "--delay-exit", "2000" }, 1, 100, true);
            return false;
        }
        catch (TimeoutException) { return true; }
    }
    private List<string> Directories()
    {
        List<string> result = new List<string>();
        for (int i = 0; i < dirBoxes.Count; i++)
        {
            string path = Environment.ExpandEnvironmentVariables(dirBoxes[i].Text.Trim().Trim('"'));
            if (path.Length > 0) { if (!Directory.Exists(path)) throw new InvalidOperationException("窗口 " + (i + 1) + " 的目录不存在：\n" + path); path = Path.GetFullPath(path); }
            result.Add(path);
        }
        return result;
    }
    internal static string SelectRotatingLogPath(string directory, int paneNumber, long maximumBytes)
    {
        if (String.IsNullOrWhiteSpace(directory)) return "";
        if (paneNumber < 1 || paneNumber > 6) throw new ArgumentOutOfRangeException("paneNumber");
        if (maximumBytes <= 0) throw new ArgumentOutOfRangeException("maximumBytes");
        Directory.CreateDirectory(directory);
        string baseName = "窗口" + paneNumber;
        for (int part = 0; ; part++)
        {
            string name = part == 0 ? baseName + ".log" : baseName + "-" + part + ".log";
            string candidate = Path.Combine(directory, name);
            if (!File.Exists(candidate) || new FileInfo(candidate).Length < maximumBytes) return candidate;
        }
    }
    private List<string> LogPaths(string logDirectory)
    {
        List<string> result = new List<string>();
        for (int i = 0; i < PaneCount; i++) result.Add(SelectRotatingLogPath(logDirectory, i + 1, LogRotationBytes));
        return result;
    }
    private List<string> PreviewLogPaths(string logDirectory)
    {
        List<string> result = new List<string>();
        for (int i = 0; i < PaneCount; i++) result.Add(Path.Combine(logDirectory, "窗口" + (i + 1) + ".log"));
        return result;
    }
    private string CreateLogSession(IList<string> directories, string shellExe, IList<string> arguments, string wtExe, string targetStrategy)
    {
        if (!recordLogs.Checked) return null;
        Directory.CreateDirectory(LogRootDirectory);
        List<string> info = new List<string>();
        info.Add("");
        info.Add("========== 启动记录 ==========");
        info.Add("启动时间=" + DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss.fff"));
        info.Add("工作台版本=" + Assembly.GetExecutingAssembly().GetName().Version);
        info.Add("Windows Terminal=" + wtExe);
        info.Add("窗口目标策略=" + targetStrategy);
        info.Add("终端程序=" + shellExe); info.Add("启动后执行命令=" + shellArguments.Text.Trim()); info.Add("实际程序参数=" + WtCommand.Join(arguments)); info.Add("窗口数量=" + PaneCount); info.Add("布局=" + (SelectedLayout == null ? "" : SelectedLayout.Text)); info.Add("启动模式=" + launchMode.Text);
        for (int i = 0; i < directories.Count; i++) info.Add("窗口" + (i + 1) + "目录=" + (String.IsNullOrWhiteSpace(directories[i]) ? "<默认目录>" : directories[i]));
        File.AppendAllLines(Path.Combine(LogRootDirectory, "启动信息.txt"), info.ToArray(), Encoding.UTF8);
        return LogRootDirectory;
    }
    private List<List<string>> BuildLaunchSteps(bool validate, bool createLogs, out string wt, out string windowTarget, out string logSession)
    {
        wt = FindTerminal(); if (validate && wt == null) throw new InvalidOperationException("找不到 Windows Terminal。请先安装，或在高级设置中选择 wt.exe。");
        string shellExe = FindExe(shell.Text); if (validate && shellExe == null) throw new InvalidOperationException("找不到终端程序：" + shell.Text + "\n如果填写的是目录，请确认目录中存在 python.exe、pwsh.exe、bash.exe 或 adb.exe。"); if (shellExe == null) shellExe = shell.Text.Trim();
        List<string> parsedShellArguments = WtCommand.BuildStartupArguments(shellExe, shellArguments.Text);
        string selectedShellName = Path.GetFileName(shellExe).ToLowerInvariant();
        bool nativePowerShellLogging = selectedShellName == "powershell.exe" || selectedShellName == "pwsh.exe";
        List<string> directories = Directories();
        // Every launch gets a unique Windows Terminal target. This always
        // creates an independent window and prevents an existing active pane
        // or another concurrent launch from changing this task's layout.
        windowTarget = "PSSW-" + Process.GetCurrentProcess().Id + "-" + DateTime.UtcNow.Ticks + "-" + Guid.NewGuid().ToString("N").Substring(0, 6);
        bool enablePaneLogs = recordLogs.Checked && nativePowerShellLogging;
        logSession = enablePaneLogs ? (createLogs ? CreateLogSession(directories, shellExe, parsedShellArguments, wt ?? "wt.exe", windowTarget) : Path.Combine(LogRootDirectory, "命令预览-不会创建文件")) : null;
        List<string> paneLogPaths = enablePaneLogs ? (createLogs ? LogPaths(logSession) : PreviewLogPaths(logSession)) : null;
        List<string> command = WtCommand.Build(PaneCount, SelectedLayout.Key, directories, shellExe, windowTarget, paneLogPaths, parsedShellArguments);
        // Fast mode submits the complete Windows Terminal command line once,
        // so all panes are created as one layout request. Standard mode
        // deliberately splits the same command into paced, focus-safe steps.
        if (LaunchModeKey == "fast") return new List<List<string>> { command };
        return WtCommand.BuildSteps(command, windowTarget);
    }

    private void ShowCommand()
    {
        try
        {
            string wt, windowTarget, logSession; List<List<string>> steps = BuildLaunchSteps(false, false, out wt, out windowTarget, out logSession); if (wt == null) wt = "wt.exe";
            StringBuilder text = new StringBuilder(); text.AppendLine("启动模式：" + launchMode.Text); text.AppendLine("窗口目标：" + windowTarget); text.AppendLine("日志目录：" + (logSession ?? "未启用")); text.AppendLine();
            for (int i = 0; i < steps.Count; i++) { text.AppendLine("步骤 " + (i + 1) + "："); text.AppendLine(WtCommand.Quote(wt) + " " + WtCommand.Join(steps[i])); if (i < steps.Count - 1) text.AppendLine("  [等待 Windows Terminal 完成布局]"); text.AppendLine(); }
            Form d = new Form { Text = "启动命令预览", StartPosition = FormStartPosition.CenterParent, Size = new Size(850, 300) };
            d.Controls.Add(new TextBox { Dock = DockStyle.Fill, Multiline = true, ReadOnly = true, ScrollBars = ScrollBars.Vertical, Font = new Font("Consolas", 10F), Text = text.ToString() }); d.ShowDialog(this);
        }
        catch (Exception ex) { MessageBox.Show(this, ex.Message, "设置有误", MessageBoxButtons.OK, MessageBoxIcon.Warning); }
    }
    private void Launch()
    {
        if (launchInProgress) return;
        try
        {
            string wt, windowTarget, logSession; List<List<string>> steps = BuildLaunchSteps(true, true, out wt, out windowTarget, out logSession);
            launchInProgress = true; launchButton.Enabled = false; launchButton.Text = "正在创建…"; status.Text = "正在创建“" + launchMode.Text + "”布局，请勿重复点击…";
            System.ComponentModel.BackgroundWorker worker = new System.ComponentModel.BackgroundWorker();
            worker.DoWork += delegate
            {
                for (int i = 0; i < steps.Count; i++)
                {
                    RunTerminalStep(wt, steps[i], i + 1);
                    if (i < steps.Count - 1) Thread.Sleep(i == 0 ? 750 : 500);
                }
            };
            worker.RunWorkerCompleted += delegate(object sender, System.ComponentModel.RunWorkerCompletedEventArgs e)
            {
                launchInProgress = false; launchButton.Enabled = true; launchButton.Text = "启动分屏";
                if (e.Error != null) { status.Text = "创建布局失败。"; MessageBox.Show(this, e.Error.Message, "启动失败", MessageBoxButtons.OK, MessageBoxIcon.Error); return; }
                status.Text = (LaunchModeKey == "fast" ? "快速布局已一次性提交。" : "标准布局命令已分步完成。") + "使用 Alt+Shift+方向键调整 pane 大小。" + (logSession == null ? "" : "日志：" + logSession); if (closeAfter.Checked) Close();
            };
            worker.RunWorkerAsync();
        }
        catch (Exception ex) { launchInProgress = false; launchButton.Enabled = true; launchButton.Text = "启动分屏"; MessageBox.Show(this, ex.Message, "启动失败", MessageBoxButtons.OK, MessageBoxIcon.Error); }
    }
}

internal static class Program
{
    private static void CleanupLegacyLogger()
    {
        string directory = AppDomain.CurrentDomain.BaseDirectory;
        List<string> oldPaths = new List<string>();
        string[] oldNames =
        {
            "PowerShellSplitWorkbench.PaneLogger.exe",
            "PowerShellSplitWorkbench.PaneLogger.legacy-delete-me.exe",
            "PowerShellSplitWorkbench.PaneLogger.pending-delete",
            "PowerShellSplitWorkbench.previous.pending-delete",
            "PowerShellSplitWorkbench.candidate.exe"
        };
        foreach (string name in oldNames) oldPaths.Add(Path.Combine(directory, name));
        try
        {
            foreach (string path in Directory.GetFiles(directory, "PowerShellSplitWorkbench.previous.*.pending-delete")) oldPaths.Add(path);
        }
        catch { }
        foreach (string path in oldPaths)
        {
            try
            {
                if (File.Exists(path)) File.Delete(path);
            }
            catch
            {
                // Old panes may still be using the previous logger. A later
                // launch will retry without interrupting those terminals.
            }
        }
    }

    private static int SelfTest()
    {
        string installerTestRoot = Path.Combine(Path.GetTempPath(), "PowerShellSplitWorkbench-InstallerTest-" + Guid.NewGuid().ToString("N"));
        string resolverTestRoot = Path.Combine(Path.GetTempPath(), "PowerShellSplitWorkbench-ResolverTest-" + Guid.NewGuid().ToString("N"));
        string mockPythonDirectory = Path.Combine(resolverTestRoot, "Python Test");
        string mockPython = Path.Combine(mockPythonDirectory, "python.exe");
        string mockBashDirectory = Path.Combine(resolverTestRoot, "Git Test", "bin");
        string mockBash = Path.Combine(mockBashDirectory, "bash.exe");
        try
        {
            if (!MainForm.EmbeddedWindowsTerminalInstallerIsValidForTest()) return 99;
            if (!MainForm.ExtractWindowsTerminalInstallerForTest(installerTestRoot)) return 100;
            if (!MainForm.TerminalTimeoutForTest()) return 101;
            using (Process cleanupTest = Process.Start(new ProcessStartInfo
            {
                FileName = Assembly.GetExecutingAssembly().Location,
                Arguments = "--delay-exit 5000",
                UseShellExecute = false,
                CreateNoWindow = true
            }))
            {
                if (cleanupTest == null) return 102;
                Thread.Sleep(100);
                if (!ProcessTree.KillTree(cleanupTest.Id) || ProcessTree.IsAlive(cleanupTest.Id)) return 103;
            }
            Directory.CreateDirectory(mockPythonDirectory);
            Directory.CreateDirectory(mockBashDirectory);
            File.WriteAllBytes(mockPython, new byte[] { 77, 90 });
            File.WriteAllBytes(mockBash, new byte[] { 77, 90 });
            string configuredPython = MainForm.FindExeForTest(mockPythonDirectory);
            if (!String.Equals(configuredPython, mockPython, StringComparison.OrdinalIgnoreCase)) return 95;
            string configuredBash = MainForm.FindExeForTest(mockBash);
            if (!String.Equals(configuredBash, mockBash, StringComparison.OrdinalIgnoreCase)) return 97;

            string resolverTarget = "PSSW-RESOLVER-TEST";
            List<string> pythonStartup = WtCommand.BuildStartupArguments(configuredPython, "print('PSSW_PYTHON_OK')");
            if (pythonStartup.Count != 3 || pythonStartup[0] != "-i" || pythonStartup[1] != "-c" || pythonStartup[2] != "print('PSSW_PYTHON_OK')") return 92;
            List<string> pythonFour = WtCommand.Build(4, "grid", new string[] { "", "", "", "" }, configuredPython, resolverTarget, null, pythonStartup);
            string pythonFourText = WtCommand.Join(pythonFour);
            if (CountExact(pythonFour, configuredPython) != 4 || CountExact(pythonFour, "-i") != 4 || CountExact(pythonFour, "-c") != 4 ||
                pythonFourText.IndexOf("PSSW_PYTHON_OK", StringComparison.Ordinal) < 0 ||
                pythonFourText.IndexOf("--pane-logger", StringComparison.OrdinalIgnoreCase) >= 0 ||
                pythonFourText.IndexOf(Path.GetFileName(WtCommand.PaneLoggerPath), StringComparison.OrdinalIgnoreCase) >= 0) return 96;

            List<string> bashStartup = WtCommand.BuildStartupArguments(configuredBash, "pwd");
            if (bashStartup.Count != 4 || bashStartup[0] != "--login" || bashStartup[1] != "-i" || bashStartup[2] != "-c" ||
                bashStartup[3].IndexOf("exec bash", StringComparison.Ordinal) < 0 || bashStartup[3].IndexOf(';') >= 0) return 93;
            List<string> bashFour = WtCommand.Build(4, "grid", new string[] { "", "", "", "" }, configuredBash, resolverTarget, null, bashStartup);
            string bashFourText = WtCommand.Join(bashFour);
            if (CountExact(bashFour, configuredBash) != 4 || CountExact(bashFour, "-c") != 4 ||
                bashFourText.IndexOf("exec bash", StringComparison.Ordinal) < 0 ||
                bashFourText.IndexOf("; exec bash", StringComparison.Ordinal) >= 0 ||
                bashFourText.IndexOf("--pane-logger", StringComparison.OrdinalIgnoreCase) >= 0 ||
                bashFourText.IndexOf(Path.GetFileName(WtCommand.PaneLoggerPath), StringComparison.OrdinalIgnoreCase) >= 0) return 98;
        }
        finally
        {
            try { if (Directory.Exists(installerTestRoot)) Directory.Delete(installerTestRoot, true); } catch { }
            try { if (Directory.Exists(resolverTestRoot)) Directory.Delete(resolverTestRoot, true); } catch { }
        }
        foreach (KeyValuePair<int, OptionItem[]> pair in WtCommand.Layouts)
            foreach (OptionItem layout in pair.Value)
            {
                List<string> dirs = new List<string>(); for (int i = 0; i < pair.Key; i++) dirs.Add(i == 0 ? @"E:\B-后装产品\1 - 版本目录\1 - 软件版本" : "");
                List<string> args = WtCommand.Build(pair.Key, layout.Key, dirs, "powershell.exe", "new"); int splits = 0;
                foreach (string arg in args) { if (arg == "split-pane") splits++; if (arg.IndexOf("Set-Location", StringComparison.OrdinalIgnoreCase) >= 0) return 20; }
                string joined = WtCommand.Join(args);
                if (splits != pair.Key - 1 || joined.IndexOf(dirs[0], StringComparison.Ordinal) < 0) return 10 + pair.Key;
                if (joined.IndexOf("Set-Location", StringComparison.OrdinalIgnoreCase) >= 0) return 22;
            }
        string strictTarget = "PSSW-SELF-TEST";
        List<string> four = WtCommand.Build(4, "grid", new string[] { "", "", "", "" }, "powershell.exe", strictTarget);
        string fourCommand = String.Join(" ", four.ToArray());
        if (fourCommand.IndexOf("split-pane -H", StringComparison.Ordinal) < 0 ||
            fourCommand.IndexOf("move-focus up", StringComparison.Ordinal) < 0) return 30;
        List<List<string>> fourSteps = WtCommand.BuildSteps(four, strictTarget);
        if (fourSteps.Count != 5) return 38;
        for (int i = 0; i < fourSteps.Count; i++)
            if (fourSteps[i].Count < 2 || fourSteps[i][0] != "-w" || fourSteps[i][1] != strictTarget) return 39;
        string quoted = WtCommand.Quote(@"E:\目录 名称\尾部\");
        if (!quoted.StartsWith("\"") || !quoted.EndsWith("\"")) return 31;
        string ps = WtCommand.Join(WtCommand.Build(2, "columns", new string[] { "", "" }, "powershell.exe", "new"));
        if (ps.IndexOf("-NoLogo", StringComparison.Ordinal) < 0 || ps.IndexOf("-NoExit", StringComparison.Ordinal) < 0) return 32;
        List<string> nativeLogArgs = WtCommand.Build(2, "columns", new string[] { "", "" }, "powershell.exe", strictTarget, new string[] { @"C:\Logs\窗口1.log", @"C:\Logs\窗口2.log" });
        string nativeLog = WtCommand.Join(nativeLogArgs);
        if (WtCommand.CountEncodedCommandsContaining(nativeLogArgs, "Start-Transcript") != 2 ||
            nativeLog.IndexOf("--pane-logger", StringComparison.Ordinal) >= 0 ||
            nativeLog.IndexOf(Path.GetFileName(WtCommand.PaneLoggerPath), StringComparison.OrdinalIgnoreCase) >= 0) return 86;
        List<string> dirInput = WtCommand.ParseShellInput("powershell.exe", "dir");
        if (dirInput.Count != 2 || dirInput[0] != "-Command" || dirInput[1] != "dir") return 87;
        List<string> dirWithLogArgs = WtCommand.Build(2, "columns", new string[] { "", "" }, "powershell.exe", strictTarget, new string[] { @"C:\Logs\窗口1.log", @"C:\Logs\窗口2.log" }, dirInput);
        string dirWithLog = WtCommand.Join(dirWithLogArgs);
        if (WtCommand.CountEncodedCommandsContaining(dirWithLogArgs, "Start-Transcript") != 2 ||
            WtCommand.CountEncodedCommandsContaining(dirWithLogArgs, "; dir") != 2 ||
            dirWithLog.IndexOf("dir -Command", StringComparison.OrdinalIgnoreCase) >= 0 ||
            dirWithLog.IndexOf("; dir", StringComparison.OrdinalIgnoreCase) >= 0 ||
            dirWithLog.IndexOf("--pane-logger", StringComparison.OrdinalIgnoreCase) >= 0) return 88;
        List<string> dirWithoutLogArgs = WtCommand.Build(2, "columns", new string[] { "", "" }, "powershell.exe", strictTarget, null, dirInput);
        if (WtCommand.CountEncodedCommandsContaining(dirWithoutLogArgs, "dir") != 2 ||
            WtCommand.Join(dirWithoutLogArgs).IndexOf(" dir", StringComparison.OrdinalIgnoreCase) >= 0) return 90;
        List<string> noProfileInput = WtCommand.ParseShellInput("powershell.exe", "-NoProfile");
        if (noProfileInput.Count != 1 || noProfileInput[0] != "-NoProfile") return 89;
        List<string> cmdStartup = WtCommand.BuildStartupArguments("cmd.exe", "dir");
        if (cmdStartup.Count != 3 || cmdStartup[0] != "/d" || cmdStartup[1] != "/k" || cmdStartup[2] != "dir") return 91;
        List<string> adbStartup = WtCommand.BuildStartupArguments("adb.exe", "-s DEVICE01 shell");
        if (adbStartup.Count != 3 || adbStartup[0] != "-s" || adbStartup[1] != "DEVICE01" || adbStartup[2] != "shell") return 94;
        string bash = WtCommand.Join(WtCommand.Build(2, "columns", new string[] { "", "" }, "bash.exe", "new"));
        if (bash.IndexOf("--login", StringComparison.Ordinal) < 0 || bash.IndexOf("-i", StringComparison.Ordinal) < 0 || bash.IndexOf("-NoLogo", StringComparison.Ordinal) >= 0) return 33;
        string cmd = WtCommand.Join(WtCommand.Build(2, "columns", new string[] { "", "" }, "cmd.exe", "new"));
        if (cmd.IndexOf("-NoLogo", StringComparison.Ordinal) >= 0 || cmd.IndexOf("-NoExit", StringComparison.Ordinal) >= 0 || cmd.IndexOf("--login", StringComparison.Ordinal) >= 0) return 34;
        string wsl = WtCommand.Join(WtCommand.Build(2, "columns", new string[] { "", "" }, "wsl.exe", "new"));
        if (wsl.IndexOf("-NoLogo", StringComparison.Ordinal) >= 0 || wsl.IndexOf("--login", StringComparison.Ordinal) >= 0) return 35;
        List<string> adbArguments = WtCommand.ParseArguments("-s \"DEVICE 01\" shell");
        if (adbArguments.Count != 3 || adbArguments[0] != "-s" || adbArguments[1] != "DEVICE 01" || adbArguments[2] != "shell") return 36;
        string adb = WtCommand.Join(WtCommand.Build(2, "columns", new string[] { "", "" }, @"D:\Android SDK\platform-tools\adb.exe", "new", null, adbArguments));
        if (adb.IndexOf("adb.exe", StringComparison.OrdinalIgnoreCase) < 0 || adb.IndexOf("\"DEVICE 01\"", StringComparison.Ordinal) < 0 || adb.IndexOf("shell", StringComparison.Ordinal) < 0) return 37;
        return 0;
    }

    private static int CountExact(IEnumerable<string> values, string expected)
    {
        int count = 0;
        foreach (string value in values) if (String.Equals(value, expected, StringComparison.OrdinalIgnoreCase)) count++;
        return count;
    }

    private static bool ContainsVisibleControl(Control parent, string text)
    {
        foreach (Control child in parent.Controls)
        {
            if (child.Visible && child.Text == text && child.Width > 0 && child.Height > 0) return true;
            if (ContainsVisibleControl(child, text)) return true;
        }
        return false;
    }

    private static int UiSelfTest()
    {
        using (MainForm form = new MainForm(false))
        {
            form.Show();
            Application.DoEvents();
            if (form.ClientSize.Width < 800 || form.ClientSize.Height < 580) return 40;
            if (form.Text != "powershell 分屏工作台 V1.3.1 - Mangetic - 2026-9-11") return 41;
            if (!ContainsVisibleControl(form, "powershell 分屏工作台")) return 42;
            if (!ContainsVisibleControl(form, "启动分屏")) return 43;
            if (!ContainsVisibleControl(form, "预览命令")) return 44;
            if (!ContainsVisibleControl(form, "窗口 1 应用到全部")) return 45;
            if (!ContainsVisibleControl(form, "全部清空")) return 46;
            if (!ContainsVisibleControl(form, "记住上次设置")) return 47;
            if (!ContainsVisibleControl(form, "保存当前方案")) return 48;
            if (!ContainsVisibleControl(form, "载入方案")) return 49;
            if (!ContainsVisibleControl(form, "记录每个窗口的运行输出")) return 76;
            if (!ContainsVisibleControl(form, "打开日志目录")) return 77;
            if (!ContainsVisibleControl(form, "清理本工具进程")) return 84;
            if (!ContainsVisibleControl(form, "安装 WT")) return 88;
            if (!ContainsVisibleControl(form, "选择程序…")) return 82;
            if (!ContainsVisibleControl(form, "启动后执行命令")) return 83;
            if (ContainsVisibleControl(form, "打开方式（仅快速模式）")) return 79;
            if (!form.SettingsAlignmentForTest) return 78;
            if (form.LaunchModeOptionCountForTest != 2) return 81;
            if (!form.RecordLogsEnabledForTest || !form.RecordLogsForTest) return 80;
            form.SelectShellForTest("cmd.exe");
            if (form.RecordLogsEnabledForTest || form.RecordLogsForTest || form.RecordLogsTextForTest.IndexOf("不支持", StringComparison.Ordinal) < 0) return 89;
            form.SelectShellForTest("powershell.exe");
            if (!form.RecordLogsEnabledForTest || !form.RecordLogsForTest || form.RecordLogsTextForTest != "记录每个窗口的运行输出") return 90;
            form.SelectLaunchModeForTest("standard");
            form.SelectPaneCountForTest(4);
            if (!form.StrictLaunchStepsForTest()) return 85;
            if (!form.FastLaunchOneShotForTest()) return 87;
            if (!form.LoggingPreviewForTest()) return 86;
            for (int paneCount = 2; paneCount <= 6; paneCount++)
            {
                form.SelectPaneCountForTest(paneCount);
                if (form.DirectoryRowCount != paneCount) return 50 + paneCount;
                if (form.LayoutOptionCount != WtCommand.Layouts[paneCount].Length) return 60 + paneCount;
            }
            form.Close();
        }
        return 0;
    }

    private static int SettingsSelfTest()
    {
        string testRoot = Path.Combine(Path.GetTempPath(), "PowerShellSplitWorkbench-SettingsTest-" + Guid.NewGuid().ToString("N"));
        string testSettings = Path.Combine(testRoot, "settings.ini");
        string testDirectory = Path.Combine(testRoot, "中文 目录");
        string previousOverride = Environment.GetEnvironmentVariable("PSSW_SETTINGS_PATH");
        try
        {
            Directory.CreateDirectory(testDirectory);
            Environment.SetEnvironmentVariable("PSSW_SETTINGS_PATH", testSettings);

            using (MainForm first = new MainForm(true))
            {
                first.Show();
                Application.DoEvents();
                first.ConfigurePersistenceTest(testDirectory);
                first.Close();
                Application.DoEvents();
            }
            if (!File.Exists(testSettings)) return 70;

            using (MainForm restored = new MainForm(true))
            {
                restored.Show();
                Application.DoEvents();
                if (restored.SelectedPaneCountForTest != 5) return 71;
                if (restored.SelectedLayoutForTest != "grid-2-3") return 72;
                if (!String.Equals(restored.FirstDirectoryForTest, testDirectory, StringComparison.Ordinal)) return 73;
                if (restored.LaunchModeForTest != "standard") return 75;
                if (!restored.RecordLogsForTest) return 76;
                if (restored.ShellArgumentsForTest != "-WindowStyle Normal") return 77;
                restored.Close();
                Application.DoEvents();
            }
        }
        catch
        {
            return 74;
        }
        finally
        {
            Environment.SetEnvironmentVariable("PSSW_SETTINGS_PATH", previousOverride);
            try { if (Directory.Exists(testRoot)) Directory.Delete(testRoot, true); } catch { }
        }
        return 0;
    }

    private static int ProfileSelfTest()
    {
        string testRoot = Path.Combine(Path.GetTempPath(), "PowerShellSplitWorkbench-ProfileTest-" + Guid.NewGuid().ToString("N"));
        string testProfiles = Path.Combine(testRoot, "profiles");
        string testDirectory = Path.Combine(testRoot, "方案目录");
        string previousOverride = Environment.GetEnvironmentVariable("PSSW_PROFILES_PATH");
        try
        {
            Directory.CreateDirectory(testDirectory); Environment.SetEnvironmentVariable("PSSW_PROFILES_PATH", testProfiles);
            using (MainForm form = new MainForm(false))
            {
                form.Show(); Application.DoEvents();
                form.ConfigureProfileTest(6, "standard", testDirectory, "cmd.exe", "/k echo profile one");
                form.SaveProfileForTest("六窗口测试");
                if (form.ProfileCountForTest != 1 || Directory.GetFiles(testProfiles, "*.ini").Length != 1) return 110;
                form.ConfigureProfileTest(2, "fast", "", "powershell.exe", "");
                form.LoadProfileForTest("六窗口测试");
                if (form.SelectedPaneCountForTest != 6 || form.LaunchModeForTest != "standard") return 111;
                if (!String.Equals(form.FirstDirectoryForTest, testDirectory, StringComparison.Ordinal)) return 112;
                if (form.ShellArgumentsForTest != "/k echo profile one") return 117;
                form.ConfigureProfileTest(5, "standard", testDirectory, "wsl.exe", "-d Ubuntu");
                form.SaveProfileForTest("六窗口测试");
                if (Directory.GetFiles(testProfiles, "*.ini").Length != 1) return 113;
                form.ConfigureProfileTest(2, "fast", "", "powershell.exe", "");
                form.LoadProfileForTest("六窗口测试");
                if (form.SelectedPaneCountForTest != 5 || form.LaunchModeForTest != "standard") return 114;
                if (form.ShellArgumentsForTest != "-d Ubuntu") return 118;
                form.DeleteProfileForTest("六窗口测试");
                if (form.ProfileCountForTest != 0 || Directory.GetFiles(testProfiles, "*.ini").Length != 0) return 115;
                form.Close();
            }
        }
        catch { return 116; }
        finally
        {
            Environment.SetEnvironmentVariable("PSSW_PROFILES_PATH", previousOverride);
            try { if (Directory.Exists(testRoot)) Directory.Delete(testRoot, true); } catch { }
        }
        return 0;
    }

    private static int LoggingSelfTest()
    {
        string testRoot = Path.Combine(Path.GetTempPath(), "PowerShellSplitWorkbench-LoggingTest-" + Guid.NewGuid().ToString("N"));
        try
        {
            Directory.CreateDirectory(testRoot);
            string batch = Path.Combine(testRoot, "writer.cmd"), log = Path.Combine(testRoot, "窗口1.log");
            File.WriteAllText(batch, "@echo off" + Environment.NewLine + "echo PSSW_LOGGING_SMOKE_TEST" + Environment.NewLine, Encoding.ASCII);
            if (!File.Exists(WtCommand.PaneLoggerPath)) return 120;
            Process process = Process.Start(new ProcessStartInfo { FileName = WtCommand.PaneLoggerPath, Arguments = "--pane-logger --log " + WtCommand.Quote(log) + " -- " + WtCommand.Quote(batch), UseShellExecute = false, CreateNoWindow = true });
            if (process == null || !process.WaitForExit(10000) || process.ExitCode != 0) return 121;
            if (!File.Exists(log) || File.ReadAllText(log).IndexOf("PSSW_LOGGING_SMOKE_TEST", StringComparison.Ordinal) < 0) return 122;
            string rotationRoot = Path.Combine(testRoot, "rotation");
            string first = MainForm.SelectRotatingLogPath(rotationRoot, 1, 5);
            if (Path.GetFileName(first) != "窗口1.log") return 124;
            File.WriteAllBytes(first, new byte[] { 1, 2, 3, 4 });
            if (!String.Equals(MainForm.SelectRotatingLogPath(rotationRoot, 1, 5), first, StringComparison.OrdinalIgnoreCase)) return 125;
            File.WriteAllBytes(first, new byte[] { 1, 2, 3, 4, 5 });
            string second = MainForm.SelectRotatingLogPath(rotationRoot, 1, 5);
            if (Path.GetFileName(second) != "窗口1-1.log") return 126;
            File.WriteAllBytes(second, new byte[] { 1, 2, 3, 4, 5 });
            string third = MainForm.SelectRotatingLogPath(rotationRoot, 1, 5);
            if (Path.GetFileName(third) != "窗口1-2.log") return 127;
            string otherPane = MainForm.SelectRotatingLogPath(rotationRoot, 2, 5);
            if (Path.GetFileName(otherPane) != "窗口2.log") return 128;
        }
        catch { return 123; }
        finally { try { if (Directory.Exists(testRoot)) Directory.Delete(testRoot, true); } catch { } }
        return 0;
    }

    private static int RenderUi(string path)
    {
        try
        {
            using (MainForm form = new MainForm(false))
            {
                form.Show();
                Application.DoEvents();
                using (Bitmap image = new Bitmap(form.Width, form.Height))
                {
                    form.DrawToBitmap(image, new Rectangle(Point.Empty, form.Size));
                    image.Save(path, System.Drawing.Imaging.ImageFormat.Png);
                }
                form.Close();
            }
            return 0;
        }
        catch { return 130; }
    }

    [STAThread]
    private static int Main(string[] args)
    {
        if (args.Length == 2 && args[0] == "--delay-exit")
        {
            int milliseconds;
            if (!Int32.TryParse(args[1], out milliseconds) || milliseconds < 0 || milliseconds > 10000) return 141;
            Thread.Sleep(milliseconds);
            return 0;
        }
        if (args.Length > 0 && args[0] == "--pane-logger") return PaneLogger.Run(args);
        CleanupLegacyLogger();
        if (args.Length == 1 && args[0] == "--self-test") return SelfTest();
        Application.EnableVisualStyles(); Application.SetCompatibleTextRenderingDefault(false);
        if (args.Length == 1 && args[0] == "--ui-self-test") return UiSelfTest();
        if (args.Length == 1 && args[0] == "--settings-self-test") return SettingsSelfTest();
        if (args.Length == 1 && args[0] == "--profile-self-test") return ProfileSelfTest();
        if (args.Length == 1 && args[0] == "--logging-self-test") return LoggingSelfTest();
        if (args.Length == 2 && args[0] == "--render-ui") return RenderUi(args[1]);
        if (args.Length == 2 && args[0] == "--cleanup-scan")
        {
            try { File.WriteAllText(args[1], MainForm.CleanupScanReport(), Encoding.UTF8); return 0; } catch { return 140; }
        }
        Application.Run(new MainForm()); return 0;
    }
}
