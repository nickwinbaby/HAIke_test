using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Reflection;
using System.Text;
using System.Threading;
using System.Windows.Forms;

[assembly: AssemblyTitle("powershell 分屏工作台 V1.1 - Mangetic - 2026-9-11")]
[assembly: AssemblyDescription("Windows Terminal PowerShell 多窗口分屏配置工具")]
[assembly: AssemblyCompany("Mangetic")]
[assembly: AssemblyProduct("powershell 分屏工作台 V1.1 - Mangetic - 2026-9-11")]
[assembly: AssemblyCopyright("Copyright © 2026")]
[assembly: AssemblyVersion("1.1.0.0")]
[assembly: AssemblyFileVersion("1.1.0.0")]

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

    private static void Pane(List<string> a, string dir, string shell)
    {
        if (!String.IsNullOrWhiteSpace(dir)) { a.Add("-d"); a.Add(dir); }
        a.Add(shell);
        string shellName = Path.GetFileName(shell).ToLowerInvariant();
        if (shellName == "powershell.exe" || shellName == "pwsh.exe")
        {
            a.Add("-NoLogo"); a.Add("-NoExit");
        }
        else if (shellName == "bash.exe")
        {
            // Git's bin\bash.exe remains embedded in Windows Terminal.
            a.Add("--login"); a.Add("-i");
        }
    }

    private static void Split(List<string> a, string direction, string dir, string shell, string size)
    {
        a.Add(";"); a.Add("split-pane"); a.Add(direction);
        if (!String.IsNullOrEmpty(size)) { a.Add("--size"); a.Add(size); }
        Pane(a, dir, shell);
    }

    private static void Focus(List<string> a, string direction)
    {
        a.Add(";"); a.Add("move-focus"); a.Add(direction);
    }

    public static List<string> Build(int count, string layout, IList<string> dirs, string shell, string target)
    {
        if (!Layouts.ContainsKey(count)) throw new ArgumentException("窗口数量必须为 2 到 6。");
        bool valid = false;
        foreach (OptionItem item in Layouts[count]) if (item.Key == layout) valid = true;
        if (!valid) throw new ArgumentException("当前窗口数量不支持所选布局。");

        string[] d = new string[count];
        for (int i = 0; i < count; i++) d[i] = i < dirs.Count ? dirs[i] : "";
        List<string> a = new List<string> { "-w", String.IsNullOrWhiteSpace(target) ? "new" : target, "new-tab" };
        Pane(a, d[0], shell);

        if (count == 2)
            Split(a, layout == "columns" ? "-V" : "-H", d[1], shell, null);
        else if (count == 3 && layout == "row")
        {
            Split(a, "-V", d[1], shell, "0.666667"); Split(a, "-V", d[2], shell, "0.5");
        }
        else if (count == 3 && layout == "column")
        {
            Split(a, "-H", d[1], shell, "0.666667"); Split(a, "-H", d[2], shell, "0.5");
        }
        else if (count == 3 && layout == "left-large")
        {
            Split(a, "-V", d[1], shell, null); Split(a, "-H", d[2], shell, null);
        }
        else if (count == 3)
        {
            Split(a, "-V", d[2], shell, null); Focus(a, "left"); Split(a, "-H", d[1], shell, null);
        }
        else if (count == 4)
        {
            // Build the bottom row first, then split the full-width top pane.
            // A single unambiguous upward focus move prevents an occasional
            // 1-pane-left/3-panes-right result from repeated lateral moves.
            Split(a, "-H", d[2], shell, null); Split(a, "-V", d[3], shell, null);
            Focus(a, "up"); Split(a, "-V", d[1], shell, null);
        }
        else if (count == 5 && layout == "grid-3-2")
        {
            Split(a, "-H", d[3], shell, null); Split(a, "-V", d[4], shell, null); Focus(a, "up");
            Split(a, "-V", d[1], shell, "0.666667"); Split(a, "-V", d[2], shell, "0.5");
        }
        else if (count == 5)
        {
            Split(a, "-H", d[2], shell, null); Focus(a, "up"); Split(a, "-V", d[1], shell, null);
            Focus(a, "down"); Split(a, "-V", d[3], shell, "0.666667"); Split(a, "-V", d[4], shell, "0.5");
        }
        else
        {
            Split(a, "-H", d[3], shell, null); Split(a, "-V", d[4], shell, "0.666667");
            Split(a, "-V", d[5], shell, "0.5"); Focus(a, "up");
            Split(a, "-V", d[1], shell, "0.666667"); Split(a, "-V", d[2], shell, "0.5");
        }
        return a;
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
            else
            {
                current.Add(arg);
            }
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
    private readonly ComboBox count = new ComboBox(), layout = new ComboBox(), target = new ComboBox();
    private readonly LayoutPreview preview = new LayoutPreview();
    private readonly TableLayoutPanel dirTable = new TableLayoutPanel();
    private readonly List<TextBox> dirBoxes = new List<TextBox>();
    private readonly Dictionary<int, string> cache = new Dictionary<int, string>();
    private readonly ComboBox shell = new ComboBox();
    private readonly TextBox terminal = new TextBox();
    private readonly CheckBox closeAfter = new CheckBox();
    private readonly CheckBox rememberSettings = new CheckBox();
    private readonly ToolStripStatusLabel status = new ToolStripStatusLabel();
    private readonly ToolTip tips = new ToolTip();
    private readonly Button launchButton = new Button();
    private readonly bool persistenceEnabled;
    private int restoredMissingDirectoryCount;
    private bool launchInProgress;

    public MainForm() : this(true) { }

    internal MainForm(bool enablePersistence)
    {
        persistenceEnabled = enablePersistence;
        Text = "powershell 分屏工作台 V1.1 - Mangetic - 2026-9-11"; StartPosition = FormStartPosition.CenterScreen;
        MinimumSize = new Size(880, 650); Size = new Size(1040, 780); Font = new Font("Microsoft YaHei UI", 9F);
        AutoScaleMode = AutoScaleMode.Dpi;
        BuildUi(); PopulateLayouts(); RebuildDirectories();
        if (persistenceEnabled) LoadSettings();
        UpdateTargetMode();
    }

    private Label MakeLabel(string text) { return new Label { Text = text, AutoSize = true, Anchor = AnchorStyles.Left, Margin = new Padding(4, 8, 7, 4) }; }
    private int PaneCount { get { return count.SelectedItem == null ? 4 : (int)count.SelectedItem; } }
    private OptionItem SelectedLayout { get { return layout.SelectedItem as OptionItem; } }
    internal int DirectoryRowCount { get { return dirBoxes.Count; } }
    internal int LayoutOptionCount { get { return layout.Items.Count; } }
    internal int SelectedPaneCountForTest { get { return PaneCount; } }
    internal string SelectedLayoutForTest { get { return SelectedLayout == null ? "" : SelectedLayout.Key; } }
    internal string FirstDirectoryForTest { get { return dirBoxes.Count == 0 ? "" : dirBoxes[0].Text; } }
    internal bool LaunchButtonEnabledForTest { get { return launchButton.Enabled; } }
    internal bool TargetEnabledForTest { get { return target.Enabled; } }
    internal string SelectedTargetForTest
    {
        get
        {
            OptionItem item = target.SelectedItem as OptionItem;
            return item == null ? "" : item.Key;
        }
    }

    internal void SelectPaneCountForTest(int value)
    {
        count.SelectedItem = value;
        Application.DoEvents();
    }

    internal void ConfigurePersistenceTest(string directory)
    {
        count.SelectedItem = 5;
        foreach (OptionItem item in layout.Items)
            if (item.Key == "grid-2-3") { layout.SelectedItem = item; break; }
        if (dirBoxes.Count > 0) dirBoxes[0].Text = directory;
        shell.Text = "powershell.exe";
        rememberSettings.Checked = true;
    }

    internal string EffectiveWindowTargetForTest(out bool strictLayout)
    {
        return EffectiveWindowTarget(out strictLayout);
    }

    private void BuildUi()
    {
        TableLayoutPanel root = new TableLayoutPanel { Dock = DockStyle.Fill, Padding = new Padding(20, 16, 20, 10), ColumnCount = 1, RowCount = 7 };
        root.RowStyles.Add(new RowStyle(SizeType.AutoSize)); root.RowStyles.Add(new RowStyle(SizeType.AutoSize)); root.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        root.RowStyles.Add(new RowStyle(SizeType.Percent, 100)); root.RowStyles.Add(new RowStyle(SizeType.AutoSize)); root.RowStyles.Add(new RowStyle(SizeType.AutoSize)); root.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        Controls.Add(root);
        root.Controls.Add(new Label { Text = "powershell 分屏工作台", AutoSize = true, Font = new Font(Font.FontFamily, 18F, FontStyle.Bold) }, 0, 0);
        root.Controls.Add(new Label { Text = "选择窗口数量、布局和目录，然后一键打开 Windows Terminal。", AutoSize = true, ForeColor = Color.DimGray, Margin = new Padding(2, 0, 0, 12) }, 0, 1);

        GroupBox settings = new GroupBox { Text = "分屏设置", Dock = DockStyle.Top, AutoSize = true, Padding = new Padding(10), Margin = new Padding(0, 0, 0, 12) };
        TableLayoutPanel sg = new TableLayoutPanel { Dock = DockStyle.Fill, AutoSize = true, ColumnCount = 7 };
        sg.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize)); sg.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 75)); sg.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize));
        sg.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100)); sg.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize)); sg.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 185)); sg.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 220));
        settings.Controls.Add(sg); root.Controls.Add(settings, 0, 2);
        count.DropDownStyle = ComboBoxStyle.DropDownList; count.Dock = DockStyle.Fill; for (int i = 2; i <= 6; i++) count.Items.Add(i); count.SelectedItem = 4;
        tips.SetToolTip(count, "选择要创建的终端 pane 数量（2–6）。");
        count.SelectedIndexChanged += delegate { PopulateLayouts(); RebuildDirectories(); UpdateTargetMode(); };
        layout.DropDownStyle = ComboBoxStyle.DropDownList; layout.Dock = DockStyle.Fill; layout.SelectedIndexChanged += delegate { RefreshPreview(); };
        tips.SetToolTip(layout, "布局预览中的编号与下方目录编号一致。");
        target.DropDownStyle = ComboBoxStyle.DropDownList; target.Dock = DockStyle.Fill;
        target.Items.Add(new OptionItem("new", "严格独立窗口（推荐）"));
        target.Items.Add(new OptionItem("last", "最近使用的窗口（2–3窗口非严格）"));
        target.Items.Add(new OptionItem("0", "编号 0 的窗口（2–3窗口非严格）"));
        target.SelectedIndex = 0;
        tips.SetToolTip(target, "4–6 个窗口始终使用唯一独立窗口，防止多次启动时布局相互干扰。");
        preview.Dock = DockStyle.Fill; preview.Margin = new Padding(12, 2, 0, 2);
        sg.Controls.Add(MakeLabel("窗口数量"), 0, 0); sg.Controls.Add(count, 1, 0); sg.Controls.Add(MakeLabel("布局"), 2, 0); sg.Controls.Add(layout, 3, 0);
        sg.Controls.Add(MakeLabel("打开方式"), 4, 0); sg.Controls.Add(target, 5, 0); sg.Controls.Add(preview, 6, 0);

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
        scroll.Controls.Add(dirTable); dirContainer.Controls.Add(dirTools, 0, 0); dirContainer.Controls.Add(scroll, 0, 1); dirs.Controls.Add(dirContainer); root.Controls.Add(dirs, 0, 3);

        GroupBox advanced = new GroupBox { Text = "高级设置", Dock = DockStyle.Top, AutoSize = true, Padding = new Padding(10), Margin = new Padding(0, 0, 0, 12) };
        TableLayoutPanel ag = new TableLayoutPanel { Dock = DockStyle.Fill, AutoSize = true, ColumnCount = 6, RowCount = 2 };
        ag.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize)); ag.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 280)); ag.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize)); ag.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100)); ag.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 80)); ag.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize));
        advanced.Controls.Add(ag); root.Controls.Add(advanced, 0, 4);
        shell.DropDownStyle = ComboBoxStyle.DropDown; shell.Dock = DockStyle.Fill; PopulateShellChoices(); shell.Text = "powershell.exe"; terminal.Dock = DockStyle.Fill;
        tips.SetToolTip(shell, "可选择 PowerShell、Git Bash、CMD、WSL，也可填写其他控制台程序的完整路径。");
        tips.SetToolTip(terminal, "留空时自动查找 Windows Terminal；自动查找失败时再手动指定 wt.exe。");
        Button chooseWt = new Button { Text = "选择…", Dock = DockStyle.Fill }; chooseWt.Click += delegate { ChooseTerminal(); };
        closeAfter.Text = "启动后关闭本窗口"; closeAfter.AutoSize = true; closeAfter.Anchor = AnchorStyles.Left;
        rememberSettings.Text = "记住上次设置"; rememberSettings.AutoSize = true; rememberSettings.Anchor = AnchorStyles.Left; rememberSettings.Checked = true;
        tips.SetToolTip(rememberSettings, "保存窗口数量、布局、目录和高级设置，下次打开时自动恢复。");
        ag.Controls.Add(MakeLabel("终端程序"), 0, 0); ag.Controls.Add(shell, 1, 0); ag.Controls.Add(MakeLabel("wt.exe"), 2, 0); ag.Controls.Add(terminal, 3, 0); ag.Controls.Add(chooseWt, 4, 0);
        ag.Controls.Add(rememberSettings, 0, 1); ag.SetColumnSpan(rememberSettings, 3);
        ag.Controls.Add(closeAfter, 3, 1); ag.SetColumnSpan(closeAfter, 3);

        FlowLayoutPanel buttons = new FlowLayoutPanel { Dock = DockStyle.Fill, AutoSize = true, FlowDirection = FlowDirection.RightToLeft, WrapContents = false, Margin = new Padding(0, 0, 0, 8) };
        launchButton.Text = "启动分屏"; launchButton.Width = 120; launchButton.Height = 34;
        launchButton.Click += delegate { Launch(); };
        Button show = new Button { Text = "预览命令", Width = 110, Height = 34 }; show.Click += delegate { ShowCommand(); };
        buttons.Controls.Add(launchButton); buttons.Controls.Add(show); root.Controls.Add(buttons, 0, 5);
        AcceptButton = launchButton;
        StatusStrip strip = new StatusStrip { SizingGrip = false }; status.Text = "准备就绪。启动后可用 Alt+Shift+方向键调整 pane 大小。"; status.Spring = true; status.TextAlign = ContentAlignment.MiddleLeft;
        strip.Items.Add(status); root.Controls.Add(strip, 0, 6);
        UpdateTargetMode();
    }

    private void UpdateTargetMode()
    {
        bool requiresStrictWindow = PaneCount >= 4;
        if (requiresStrictWindow && target.Items.Count > 0) target.SelectedIndex = 0;
        target.Enabled = !requiresStrictWindow;
        if (requiresStrictWindow)
            tips.SetToolTip(target, "4–6 个窗口已锁定为严格独立窗口，防止焦点竞争造成比例异常。");
        else
            tips.SetToolTip(target, "严格独立窗口最稳定；现有窗口模式可能受到当前活动 pane 影响。");
    }

    protected override void OnShown(EventArgs e)
    {
        base.OnShown(e);
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
        if (launchInProgress)
        {
            e.Cancel = true;
            status.Text = "严格布局正在创建，请稍候完成后再关闭。";
            return;
        }
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

            if (values.TryGetValue("target", out raw))
                foreach (OptionItem item in target.Items)
                    if (item.Key == raw) { target.SelectedItem = item; break; }
            UpdateTargetMode();

            if (values.TryGetValue("shell", out raw)) shell.Text = DecodeSetting(raw);
            if (values.TryGetValue("terminal", out raw)) terminal.Text = DecodeSetting(raw);
            if (values.TryGetValue("closeAfter", out raw)) closeAfter.Checked = raw == "1";

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
            lines.Add("version=1");
            lines.Add("remember=1");
            lines.Add("count=" + PaneCount);
            lines.Add("layout=" + (SelectedLayout == null ? "" : SelectedLayout.Key));
            OptionItem selectedTarget = target.SelectedItem as OptionItem;
            lines.Add("target=" + (selectedTarget == null ? "new" : selectedTarget.Key));
            lines.Add("shell=" + EncodeSetting(shell.Text));
            lines.Add("terminal=" + EncodeSetting(terminal.Text));
            lines.Add("closeAfter=" + (closeAfter.Checked ? "1" : "0"));
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

    private static string FindExe(string value)
    {
        if (String.IsNullOrWhiteSpace(value)) return null; value = Environment.ExpandEnvironmentVariables(value.Trim().Trim('"'));
        if (File.Exists(value)) return Path.GetFullPath(value); if (value.Contains("\\") || value.Contains("/")) return null;
        foreach (string raw in (Environment.GetEnvironmentVariable("PATH") ?? "").Split(Path.PathSeparator))
        { try { string file = Path.Combine(raw.Trim().Trim('"'), value); if (File.Exists(file)) return file; } catch { } }
        return null;
    }
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
        foreach (string path in paths) if (File.Exists(path)) return path; return null;
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
    private List<string> Arguments(bool validate, out string wt)
    {
        wt = FindTerminal(); if (validate && wt == null) throw new InvalidOperationException("找不到 Windows Terminal。请先安装，或在高级设置中选择 wt.exe。");
        string shellExe = FindExe(shell.Text); if (validate && shellExe == null) throw new InvalidOperationException("找不到 Shell：" + shell.Text); if (shellExe == null) shellExe = shell.Text.Trim();
        OptionItem t = target.SelectedItem as OptionItem; return WtCommand.Build(PaneCount, SelectedLayout.Key, Directories(), shellExe, t == null ? "new" : t.Key);
    }

    private string EffectiveWindowTarget(out bool strictLayout)
    {
        OptionItem selected = target.SelectedItem as OptionItem;
        string requested = selected == null ? "new" : selected.Key;
        strictLayout = requested == "new" || PaneCount >= 4;
        if (!strictLayout) return requested;
        return "PSSW-" + Process.GetCurrentProcess().Id + "-" + DateTime.UtcNow.Ticks + "-" + Guid.NewGuid().ToString("N").Substring(0, 6);
    }

    private List<List<string>> BuildLaunchSteps(bool validate, out string wt, out string windowTarget, out bool strictLayout)
    {
        List<string> directories = Directories();
        wt = FindTerminal();
        if (validate && wt == null) throw new InvalidOperationException("找不到 Windows Terminal。请先安装，或在高级设置中选择 wt.exe。");
        string shellExe = FindExe(shell.Text);
        if (validate && shellExe == null) throw new InvalidOperationException("找不到 Shell：" + shell.Text);
        if (shellExe == null) shellExe = shell.Text.Trim();
        windowTarget = EffectiveWindowTarget(out strictLayout);
        List<string> command = WtCommand.Build(PaneCount, SelectedLayout.Key, directories, shellExe, windowTarget);
        return WtCommand.BuildSteps(command, windowTarget);
    }
    private void ShowCommand()
    {
        try
        {
            string wt, windowTarget; bool strictLayout;
            List<List<string>> steps = BuildLaunchSteps(false, out wt, out windowTarget, out strictLayout);
            if (wt == null) wt = "wt.exe";
            StringBuilder previewText = new StringBuilder();
            previewText.AppendLine(strictLayout ? "严格布局：逐步执行，每一步间隔等待" : "非严格布局：操作现有 Terminal 窗口");
            previewText.AppendLine("窗口目标：" + windowTarget);
            previewText.AppendLine();
            for (int i = 0; i < steps.Count; i++)
            {
                previewText.AppendLine("步骤 " + (i + 1) + "：");
                previewText.AppendLine(WtCommand.Quote(wt) + " " + WtCommand.Join(steps[i]));
                if (i < steps.Count - 1) previewText.AppendLine("  [等待 Windows Terminal 完成布局]");
                previewText.AppendLine();
            }
            Form d = new Form { Text = "启动命令预览", StartPosition = FormStartPosition.CenterParent, Size = new Size(850, 300) };
            d.Controls.Add(new TextBox { Dock = DockStyle.Fill, Multiline = true, ReadOnly = true, ScrollBars = ScrollBars.Vertical, Font = new Font("Consolas", 10F), Text = previewText.ToString() }); d.ShowDialog(this);
        }
        catch (Exception ex) { MessageBox.Show(this, ex.Message, "设置有误", MessageBoxButtons.OK, MessageBoxIcon.Warning); }
    }
    private void Launch()
    {
        if (launchInProgress) return;
        try
        {
            string wt, windowTarget; bool strictLayout;
            List<List<string>> steps = BuildLaunchSteps(true, out wt, out windowTarget, out strictLayout);
            launchInProgress = true;
            launchButton.Enabled = false;
            launchButton.Text = "正在创建…";
            status.Text = strictLayout
                ? "正在创建严格布局，请勿重复点击或操作目标 Terminal 窗口…"
                : "正在向现有 Terminal 窗口发送分屏命令…";

            System.ComponentModel.BackgroundWorker worker = new System.ComponentModel.BackgroundWorker();
            worker.DoWork += delegate(object sender, System.ComponentModel.DoWorkEventArgs e)
            {
                for (int i = 0; i < steps.Count; i++)
                {
                    Process process = Process.Start(new ProcessStartInfo
                    {
                        FileName = wt,
                        Arguments = WtCommand.Join(steps[i]),
                        UseShellExecute = false,
                        WorkingDirectory = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile),
                        CreateNoWindow = true
                    });
                    if (process != null)
                    {
                        process.WaitForExit(5000);
                        if (process.HasExited && process.ExitCode != 0)
                            throw new InvalidOperationException("Windows Terminal 步骤 " + (i + 1) + " 执行失败，退出码：" + process.ExitCode);
                    }
                    if (i < steps.Count - 1) Thread.Sleep(i == 0 ? 750 : 500);
                }
            };
            worker.RunWorkerCompleted += delegate(object sender, System.ComponentModel.RunWorkerCompletedEventArgs e)
            {
                launchInProgress = false;
                launchButton.Enabled = true;
                launchButton.Text = "启动分屏";
                if (e.Error != null)
                {
                    status.Text = "创建布局失败。";
                    MessageBox.Show(this, e.Error.Message, "启动失败", MessageBoxButtons.OK, MessageBoxIcon.Error);
                    return;
                }
                status.Text = strictLayout
                    ? "严格布局已创建完成。使用 Alt+Shift+方向键调整 pane 大小。"
                    : "分屏命令已完成（现有窗口模式不保证严格布局）。";
                if (closeAfter.Checked) Close();
            };
            worker.RunWorkerAsync();
        }
        catch (Exception ex)
        {
            launchInProgress = false;
            launchButton.Enabled = true;
            launchButton.Text = "启动分屏";
            status.Text = "创建布局失败。";
            MessageBox.Show(this, ex.Message, "启动失败", MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
    }
}

internal static class Program
{
    private static int SelfTest()
    {
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
        List<string> four = WtCommand.Build(4, "grid", new string[] { "", "", "", "" }, "powershell.exe", "new");
        string fourCommand = String.Join(" ", four.ToArray());
        if (fourCommand.IndexOf("split-pane -H", StringComparison.Ordinal) < 0 ||
            fourCommand.IndexOf("move-focus up", StringComparison.Ordinal) < 0) return 30;
        string quoted = WtCommand.Quote(@"E:\目录 名称\尾部\");
        if (!quoted.StartsWith("\"") || !quoted.EndsWith("\"")) return 31;
        const string strictTarget = "PSSW-self-test-window";
        List<string> six = WtCommand.Build(6, "grid-3x2", new string[] { "", "", "", "", "", "" }, "powershell.exe", strictTarget);
        List<List<string>> sixSteps = WtCommand.BuildSteps(six, strictTarget);
        // One initial new-tab + five split-pane actions + one move-focus action.
        if (sixSteps.Count != 7) return 32;
        int splitStepCount = 0;
        int focusStepCount = 0;
        foreach (List<string> step in sixSteps)
        {
            if (step.Count < 3 || step[0] != "-w" || step[1] != strictTarget) return 33;
            if (step.Contains(";")) return 34;
            if (step.Contains("split-pane")) splitStepCount++;
            if (step.Contains("move-focus")) focusStepCount++;
        }
        if (splitStepCount != 5 || focusStepCount != 1) return 35;
        string ps = WtCommand.Join(WtCommand.Build(2, "columns", new string[] { "", "" }, "powershell.exe", "new"));
        if (ps.IndexOf("-NoLogo", StringComparison.Ordinal) < 0 || ps.IndexOf("-NoExit", StringComparison.Ordinal) < 0) return 36;
        string bash = WtCommand.Join(WtCommand.Build(2, "columns", new string[] { "", "" }, @"D:\Program Files\Git\bin\bash.exe", "new"));
        if (bash.IndexOf("--login", StringComparison.Ordinal) < 0 || bash.IndexOf("-i", StringComparison.Ordinal) < 0 || bash.IndexOf("-NoLogo", StringComparison.Ordinal) >= 0) return 37;
        string cmd = WtCommand.Join(WtCommand.Build(2, "columns", new string[] { "", "" }, "cmd.exe", "new"));
        if (cmd.IndexOf("-NoLogo", StringComparison.Ordinal) >= 0 || cmd.IndexOf("-NoExit", StringComparison.Ordinal) >= 0 || cmd.IndexOf("--login", StringComparison.Ordinal) >= 0) return 38;
        string wsl = WtCommand.Join(WtCommand.Build(2, "columns", new string[] { "", "" }, "wsl.exe", "new"));
        if (wsl.IndexOf("-NoLogo", StringComparison.Ordinal) >= 0 || wsl.IndexOf("--login", StringComparison.Ordinal) >= 0) return 39;
        return 0;
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
            if (form.Text != "powershell 分屏工作台 V1.1 - Mangetic - 2026-9-11") return 41;
            if (!ContainsVisibleControl(form, "powershell 分屏工作台")) return 42;
            if (!ContainsVisibleControl(form, "启动分屏")) return 43;
            if (!ContainsVisibleControl(form, "预览命令")) return 44;
            if (!ContainsVisibleControl(form, "窗口 1 应用到全部")) return 45;
            if (!ContainsVisibleControl(form, "全部清空")) return 46;
            if (!ContainsVisibleControl(form, "记住上次设置")) return 47;
            if (!form.LaunchButtonEnabledForTest) return 48;
            for (int paneCount = 2; paneCount <= 6; paneCount++)
            {
                form.SelectPaneCountForTest(paneCount);
                if (form.DirectoryRowCount != paneCount) return 50 + paneCount;
                if (form.LayoutOptionCount != WtCommand.Layouts[paneCount].Length) return 60 + paneCount;
                bool strict;
                string effectiveTarget = form.EffectiveWindowTargetForTest(out strict);
                if (paneCount >= 4 && (!strict || !effectiveTarget.StartsWith("PSSW-", StringComparison.Ordinal))) return 80 + paneCount;
                if (paneCount >= 4 && (form.TargetEnabledForTest || form.SelectedTargetForTest != "new")) return 90 + paneCount;
                if (paneCount <= 3 && !form.TargetEnabledForTest) return 100 + paneCount;
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

    [STAThread]
    private static int Main(string[] args)
    {
        if (args.Length == 1 && args[0] == "--self-test") return SelfTest();
        Application.EnableVisualStyles(); Application.SetCompatibleTextRenderingDefault(false);
        if (args.Length == 1 && args[0] == "--ui-self-test") return UiSelfTest();
        if (args.Length == 1 && args[0] == "--settings-self-test") return SettingsSelfTest();
        Application.Run(new MainForm()); return 0;
    }
}
