// BAPBAP Korean patch GUI. Thin wrapper around install.ps1 / uninstall.ps1, embedded as resources.
// Builds with the csc.exe that ships with Windows (C# 5, .NET Framework 4.x). See build_gui.ps1.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Windows.Forms;
using Microsoft.Win32;

internal static class Engine
{
    private const string ResourcePrefix = "bundle/";

    public const long RequiredTempBytes = 3L * 1024 * 1024 * 1024;
    public const long RequiredGameBytes = 1L * 1024 * 1024 * 1024;

    public static string Extract()
    {
        string dir = Path.Combine(Path.GetTempPath(), "bapko-tool-" + Guid.NewGuid().ToString("N"));
        Assembly asm = Assembly.GetExecutingAssembly();
        foreach (string name in asm.GetManifestResourceNames())
        {
            if (!name.StartsWith(ResourcePrefix, StringComparison.Ordinal))
                continue;
            string target = Path.Combine(dir, name.Substring(ResourcePrefix.Length).Replace('/', Path.DirectorySeparatorChar));
            Directory.CreateDirectory(Path.GetDirectoryName(target));
            using (Stream input = asm.GetManifestResourceStream(name))
            using (FileStream output = File.Create(target))
                input.CopyTo(output);
        }
        return dir;
    }

    public static void Cleanup(string dir)
    {
        try
        {
            if (dir != null && Directory.Exists(dir))
                Directory.Delete(dir, true);
        }
        catch (IOException) { }
        catch (UnauthorizedAccessException) { }
    }

    // Runs a bundled script and returns its exit code. Output lines go to onLine.
    public static int RunScript(string extracted, string script, string gameDir, bool dryRun, Action<string> onLine)
    {
        string system = Environment.GetFolderPath(Environment.SpecialFolder.System);
        var psi = new ProcessStartInfo
        {
            FileName = Path.Combine(system, @"WindowsPowerShell\v1.0\powershell.exe"),
            Arguments = "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File " + Quote(Path.Combine(extracted, script))
                + " -GameDir " + Quote(gameDir) + (dryRun ? " -DryRun" : ""),
            WorkingDirectory = extracted,
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true
        };
        // A PowerShell 7 parent leaves module paths that stop Windows PowerShell finding its own modules.
        psi.EnvironmentVariables.Remove("PSModulePath");
        Encoding oem = Encoding.GetEncoding(CultureInfo.CurrentCulture.TextInfo.OEMCodePage);
        psi.StandardOutputEncoding = oem;
        psi.StandardErrorEncoding = oem;
        using (var process = new Process { StartInfo = psi })
        {
            DataReceivedEventHandler handler = (s, e) =>
            {
                if (e.Data != null)
                    onLine(e.Data);
            };
            process.OutputDataReceived += handler;
            process.ErrorDataReceived += handler;
            process.Start();
            process.BeginOutputReadLine();
            process.BeginErrorReadLine();
            process.WaitForExit();
            return process.ExitCode;
        }
    }

    private static string Quote(string value)
    {
        return "\"" + value.TrimEnd('\\') + "\"";
    }

    public static bool IsGameFolder(string dir)
    {
        return !string.IsNullOrWhiteSpace(dir)
            && File.Exists(Path.Combine(dir, "bapbap.exe"))
            && File.Exists(Path.Combine(dir, @"bapbap_Data\sharedassets0.assets"));
    }

    public static string FindGameFolder()
    {
        var candidates = new List<string>();
        try
        {
            using (RegistryKey key = Registry.CurrentUser.OpenSubKey(@"Software\Valve\Steam"))
            {
                string steam = key == null ? null : key.GetValue("SteamPath") as string;
                if (!string.IsNullOrEmpty(steam))
                {
                    candidates.Add(Path.Combine(steam, @"steamapps\common\BAPBAP"));
                    string vdf = Path.Combine(steam, @"steamapps\libraryfolders.vdf");
                    if (File.Exists(vdf))
                    {
                        foreach (Match m in Regex.Matches(File.ReadAllText(vdf), "\"path\"\\s+\"([^\"]+)\""))
                            candidates.Add(Path.Combine(m.Groups[1].Value.Replace(@"\\", @"\"), @"steamapps\common\BAPBAP"));
                    }
                }
            }
        }
        catch (Exception ex)
        {
            if (!(ex is IOException || ex is UnauthorizedAccessException || ex is System.Security.SecurityException))
                throw;
        }
        candidates.Add(@"C:\Program Files (x86)\Steam\steamapps\common\BAPBAP");
        candidates.Add(@"C:\Program Files\Steam\steamapps\common\BAPBAP");
        foreach (string candidate in candidates)
        {
            try
            {
                string full = Path.GetFullPath(candidate);
                if (IsGameFolder(full))
                    return full;
            }
            catch (ArgumentException) { }
            catch (NotSupportedException) { }
        }
        return "";
    }

    // BapAssetTool.exe is a framework-dependent .NET 8 program.
    public static bool HasDotNet8()
    {
        var roots = new List<string>();
        string env = Environment.GetEnvironmentVariable("DOTNET_ROOT");
        if (!string.IsNullOrEmpty(env))
            roots.Add(env);
        roots.Add(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles), "dotnet"));
        foreach (string root in roots)
        {
            string shared = Path.Combine(root, @"shared\Microsoft.NETCore.App");
            if (Directory.Exists(shared) && Directory.GetDirectories(shared, "8.*").Length > 0)
                return true;
        }
        return false;
    }

    public static bool IsGameRunning()
    {
        Process[] found = Process.GetProcessesByName("bapbap");
        foreach (Process p in found)
            p.Dispose();
        return found.Length > 0;
    }

    public static bool CanWrite(string gameDir)
    {
        string probe = Path.Combine(gameDir, @"bapbap_Data\.bapko-write-test");
        try
        {
            File.WriteAllText(probe, "");
            File.Delete(probe);
            return true;
        }
        catch (UnauthorizedAccessException) { return false; }
        catch (IOException) { return false; }
    }

    public static long FreeBytes(string path)
    {
        return new DriveInfo(Path.GetPathRoot(Path.GetFullPath(path))).AvailableFreeSpace;
    }

    public static string ExplainFailure(string log)
    {
        if (log.Contains("Unsupported or modified game files"))
            return "지원하지 않는 버전이거나 다른 방식으로 수정된 게임 파일입니다.\r\n\r\nSteam에서 BAPBAP 속성 > 설치된 파일 > 게임 파일 무결성 검사를 한 뒤 다시 시도해 주세요.";
        if (log.Contains("BAPBAP is running"))
            return "게임이 실행 중입니다. 게임을 완전히 종료한 뒤 다시 시도해 주세요.";
        if (log.Contains("No backup found") || log.Contains("Backup missing"))
            return "되돌릴 백업이 없습니다.\r\n\r\nSteam의 게임 파일 무결성 검사로 원본을 복구할 수 있습니다.";
        if (log.Contains("unknown/modified"))
            return "게임 파일이 알 수 없는 상태라 덮어쓰지 않았습니다.\r\n\r\nSteam의 게임 파일 무결성 검사로 원본을 복구할 수 있습니다.";
        return "작업에 실패했습니다. 게임 파일이 교체되기 전 단계라면 변경된 내용은 없습니다.\r\n\r\n자세한 내용은 로그를 확인해 주세요.";
    }
}

internal sealed class MainForm : Form
{
    private const string Version = "2.0.0";

    private readonly TextBox _path = new TextBox();
    private readonly Button _browse = new Button();
    private readonly Button _install = new Button();
    private readonly Button _uninstall = new Button();
    private readonly Label _status = new Label();
    private readonly ProgressBar _progress = new ProgressBar();
    private readonly TextBox _log = new TextBox();
    private readonly StringBuilder _logText = new StringBuilder();
    private bool _busy;

    public MainForm(string initialPath)
    {
        Text = "BAPBAP 한글 패치 " + Version;
        Font = new Font("Malgun Gothic", 9.5f);
        AutoScaleMode = AutoScaleMode.Dpi;
        ClientSize = new Size(620, 430);
        FormBorderStyle = FormBorderStyle.FixedSingle;
        MaximizeBox = false;
        StartPosition = FormStartPosition.CenterScreen;

        var title = new Label { Text = "BAPBAP 비공식 한국어 패치", Font = new Font("Malgun Gothic", 15f, FontStyle.Bold), AutoSize = true, Location = new Point(16, 12) };
        var note = new Label { Text = "설치 후 게임 설정에서 언어를 Türkçe로 선택하면 한국어로 표시됩니다.", AutoSize = true, ForeColor = Color.DimGray, Location = new Point(18, 48) };
        var pathLabel = new Label { Text = "게임 폴더", AutoSize = true, Location = new Point(18, 84) };

        _path.Location = new Point(18, 106);
        _path.Size = new Size(490, 26);
        _path.Text = initialPath;
        _path.TextChanged += (s, e) => UpdateState();

        _browse.Text = "찾아보기";
        _browse.Location = new Point(516, 104);
        _browse.Size = new Size(86, 30);
        _browse.Click += OnBrowse;

        _status.AutoSize = false;
        _status.Location = new Point(18, 138);
        _status.Size = new Size(584, 24);

        _install.Text = "한글 패치 설치";
        _install.Font = new Font("Malgun Gothic", 10.5f, FontStyle.Bold);
        _install.Location = new Point(18, 168);
        _install.Size = new Size(240, 42);
        _install.Click += (s, e) => Start("install.ps1");

        _uninstall.Text = "패치 제거";
        _uninstall.Location = new Point(266, 168);
        _uninstall.Size = new Size(120, 42);
        _uninstall.Click += (s, e) => Start("uninstall.ps1");

        _progress.Location = new Point(18, 222);
        _progress.Size = new Size(584, 10);
        _progress.Style = ProgressBarStyle.Blocks;

        _log.Location = new Point(18, 242);
        _log.Size = new Size(584, 172);
        _log.Multiline = true;
        _log.ReadOnly = true;
        _log.ScrollBars = ScrollBars.Vertical;
        _log.BackColor = SystemColors.Window;
        _log.Font = new Font("Consolas", 8.5f);

        Controls.AddRange(new Control[] { title, note, pathLabel, _path, _browse, _status, _install, _uninstall, _progress, _log });
        FormClosing += (s, e) =>
        {
            if (_busy)
            {
                MessageBox.Show(this, "작업이 끝날 때까지 기다려 주세요.", Text, MessageBoxButtons.OK, MessageBoxIcon.Information);
                e.Cancel = true;
            }
        };
        UpdateState();
    }

    private string GameDir { get { return _path.Text.Trim().Trim('"').TrimEnd('\\'); } }

    private void UpdateState()
    {
        bool ok = Engine.IsGameFolder(GameDir);
        _install.Enabled = ok && !_busy;
        _uninstall.Enabled = ok && !_busy;
        _path.Enabled = !_busy;
        _browse.Enabled = !_busy;
        if (_busy)
            return;
        if (ok)
        {
            _status.ForeColor = Color.SeaGreen;
            _status.Text = "BAPBAP 폴더를 찾았습니다.";
        }
        else
        {
            _status.ForeColor = Color.Firebrick;
            _status.Text = "bapbap.exe가 있는 폴더를 지정해 주세요.";
        }
    }

    private void OnBrowse(object sender, EventArgs e)
    {
        using (var dialog = new FolderBrowserDialog())
        {
            dialog.Description = "bapbap.exe가 있는 폴더를 선택하세요.";
            dialog.ShowNewFolderButton = false;
            if (Directory.Exists(GameDir))
                dialog.SelectedPath = GameDir;
            if (dialog.ShowDialog(this) == DialogResult.OK)
                _path.Text = dialog.SelectedPath;
        }
    }

    private bool Precheck(bool installing)
    {
        string dir = GameDir;
        if (Engine.IsGameRunning())
        {
            MessageBox.Show(this, "게임이 실행 중입니다. 게임을 완전히 종료한 뒤 다시 시도해 주세요.", Text, MessageBoxButtons.OK, MessageBoxIcon.Warning);
            return false;
        }
        if (!Engine.CanWrite(dir))
        {
            DialogResult answer = MessageBox.Show(this, "이 폴더에 쓸 권한이 없습니다. 관리자 권한으로 다시 실행할까요?", Text, MessageBoxButtons.YesNo, MessageBoxIcon.Question);
            if (answer == DialogResult.Yes)
                RestartElevated(dir);
            return false;
        }
        if (!installing)
            return true;
        if (!Engine.HasDotNet8())
        {
            DialogResult answer = MessageBox.Show(this, "패치에 .NET 8 Runtime이 필요합니다. Microsoft 다운로드 페이지를 열까요?\r\n\r\n.NET Runtime 8.x의 Windows x64 설치 파일을 설치한 뒤 다시 실행해 주세요.", Text, MessageBoxButtons.YesNo, MessageBoxIcon.Information);
            if (answer == DialogResult.Yes)
                Process.Start("https://dotnet.microsoft.com/download/dotnet/8.0");
            return false;
        }
        long temp = Engine.FreeBytes(Path.GetTempPath());
        long game = Engine.FreeBytes(dir);
        if (temp < Engine.RequiredTempBytes || game < Engine.RequiredGameBytes)
        {
            MessageBox.Show(this, "디스크 공간이 부족합니다.\r\n\r\n임시 폴더 드라이브에 3GB, 게임 드라이브에 1GB 이상의 여유 공간이 필요합니다.", Text, MessageBoxButtons.OK, MessageBoxIcon.Warning);
            return false;
        }
        return true;
    }

    private void RestartElevated(string dir)
    {
        try
        {
            Process.Start(new ProcessStartInfo
            {
                FileName = Application.ExecutablePath,
                Arguments = "\"" + dir + "\"",
                UseShellExecute = true,
                Verb = "runas"
            });
            Close();
        }
        catch (System.ComponentModel.Win32Exception) { }
    }

    private void Start(string script)
    {
        bool installing = script == "install.ps1";
        if (!Precheck(installing))
            return;
        string question = installing
            ? "다음 폴더에 한글 패치를 설치합니다.\r\n\r\n" + GameDir + "\r\n\r\n현재 게임 파일은 폴더 안의 .bapko-backup에 백업됩니다. 몇 분 걸릴 수 있습니다."
            : "다음 폴더에서 패치를 제거하고 백업으로 되돌립니다.\r\n\r\n" + GameDir;
        if (MessageBox.Show(this, question, Text, MessageBoxButtons.OKCancel, MessageBoxIcon.Question) != DialogResult.OK)
            return;

        _busy = true;
        _logText.Clear();
        _log.Clear();
        _progress.Style = ProgressBarStyle.Marquee;
        _status.ForeColor = SystemColors.ControlText;
        _status.Text = installing ? "패치 설치 중입니다. 창을 닫지 마세요..." : "패치 제거 중입니다. 창을 닫지 마세요...";
        UpdateState();

        string dir = GameDir;
        var worker = new Thread(() => Work(script, dir, installing)) { IsBackground = true };
        worker.Start();
    }

    private void Work(string script, string dir, bool installing)
    {
        int code = -1;
        string extracted = null;
        try
        {
            extracted = Engine.Extract();
            code = Engine.RunScript(extracted, script, dir, false, Append);
        }
        catch (Exception ex)
        {
            Append(ex.Message);
        }
        finally
        {
            Engine.Cleanup(extracted);
        }
        BeginInvoke((Action)(() => Finish(code, installing)));
    }

    private void Append(string line)
    {
        BeginInvoke((Action)(() =>
        {
            _logText.AppendLine(line);
            _log.AppendText(line + Environment.NewLine);
        }));
    }

    private void Finish(int code, bool installing)
    {
        _busy = false;
        _progress.Style = ProgressBarStyle.Blocks;
        UpdateState();
        if (code == 0)
        {
            _status.ForeColor = Color.SeaGreen;
            _status.Text = installing ? "설치가 끝났습니다." : "제거가 끝났습니다.";
            string done = installing
                ? "한글 패치 설치가 끝났습니다.\r\n\r\n게임 설정에서 언어를 Türkçe로 선택해 주세요."
                : _logText.ToString().Contains("previous patch (v1)")
                    ? "이전 패치(v1) 상태로 되돌렸습니다.\r\n\r\nSteam 원본이 필요하면 게임 파일 무결성 검사를 실행해 주세요."
                    : "패치를 제거하고 원본으로 되돌렸습니다.";
            MessageBox.Show(this, done, Text, MessageBoxButtons.OK, MessageBoxIcon.Information);
        }
        else
        {
            _status.ForeColor = Color.Firebrick;
            _status.Text = "실패했습니다. 아래 로그를 확인해 주세요.";
            MessageBox.Show(this, Engine.ExplainFailure(_logText.ToString()), Text, MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
    }

    // QA only: renders the window itself, so no desktop content is captured.
    public void SaveScreenshot(string path)
    {
        Opacity = 0;
        ShowInTaskbar = false;
        Show();
        Application.DoEvents();
        using (var bitmap = new Bitmap(Width, Height))
        {
            DrawToBitmap(bitmap, new Rectangle(0, 0, Width, Height));
            bitmap.Save(path, System.Drawing.Imaging.ImageFormat.Png);
        }
    }
}

internal static class Program
{
    [STAThread]
    private static int Main(string[] args)
    {
        // QA entry points; end users never pass these.
        if (args.Length == 4 && args[0] == "--test-run")
            return TestRun(args[1], args[2], args[3]);
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        if (args.Length == 2 && args[0] == "--test-shot")
        {
            using (var form = new MainForm(Engine.FindGameFolder()))
                form.SaveScreenshot(args[1]);
            return 0;
        }
        string initial = args.Length == 1 ? args[0] : Engine.FindGameFolder();
        Application.Run(new MainForm(initial));
        return 0;
    }

    private static int TestRun(string mode, string gameDir, string logPath)
    {
        string extracted = Engine.Extract();
        var lines = new List<string>();
        try
        {
            string script = mode == "uninstall" ? "uninstall.ps1" : "install.ps1";
            int code = Engine.RunScript(extracted, script, gameDir, mode == "dryrun", line => { lock (lines) lines.Add(line); });
            lock (lines)
            {
                lines.Add("exit=" + code.ToString(CultureInfo.InvariantCulture));
                File.WriteAllLines(logPath, lines.ToArray(), new UTF8Encoding(false));
            }
            return code;
        }
        finally
        {
            Engine.Cleanup(extracted);
        }
    }
}
