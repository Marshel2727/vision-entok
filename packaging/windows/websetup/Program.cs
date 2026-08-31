using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.Globalization;
using System.IO;
using System.Net;
using System.Security.Cryptography;
using System.Threading;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Windows.Forms;

namespace EntokVisionWebSetup
{
    internal sealed class DownloadFile
    {
        public string name { get; set; }
        public string url { get; set; }
        public long size { get; set; }
        public string sha256 { get; set; }
        public bool installer { get; set; }
    }

    internal sealed class DownloadVariant
    {
        public string label { get; set; }
        public List<DownloadFile> files { get; set; }
    }

    internal sealed class ReleaseManifest
    {
        public string version { get; set; }
        public string release_url { get; set; }
        public Dictionary<string, DownloadVariant> variants { get; set; }
    }

    internal sealed class DownloadProgress
    {
        public string FileName { get; set; }
        public int Percent { get; set; }
    }

    internal sealed class SetupForm : Form
    {
        private readonly ComboBox variantBox = new ComboBox();
        private readonly Button installButton = new Button();
        private readonly Label statusLabel = new Label();
        private readonly ProgressBar progressBar = new ProgressBar();
        private ReleaseManifest manifest;

        internal SetupForm()
        {
            Text = "Entok Vision Lite WebSetup";
            ClientSize = new Size(560, 245);
            MinimumSize = new Size(520, 280);
            StartPosition = FormStartPosition.CenterScreen;
            Font = new Font("Segoe UI", 10F);

            var title = new Label
            {
                Text = "Entok Vision Lite " + WebSetupConfig.AppVersion,
                Font = new Font("Segoe UI Semibold", 16F),
                AutoSize = true,
                Location = new Point(24, 20)
            };
            var hint = new Label
            {
                Text = "Pilih paket CPU atau GPU. Unduhan yang terputus akan dilanjutkan.",
                AutoSize = true,
                Location = new Point(26, 58)
            };
            variantBox.DropDownStyle = ComboBoxStyle.DropDownList;
            variantBox.Items.AddRange(new object[] { "CPU", "GPU-CUDA124" });
            variantBox.SelectedIndex = 0;
            variantBox.Location = new Point(28, 92);
            variantBox.Width = 210;

            installButton.Text = "Unduh dan Pasang";
            installButton.Location = new Point(258, 90);
            installButton.Size = new Size(165, 33);
            installButton.Enabled = false;
            installButton.Click += async (sender, args) => await InstallSelectedAsync();

            progressBar.Location = new Point(28, 145);
            progressBar.Size = new Size(500, 22);
            statusLabel.Text = "Memuat manifest rilis...";
            statusLabel.AutoEllipsis = true;
            statusLabel.Location = new Point(28, 180);
            statusLabel.Size = new Size(500, 42);

            Controls.Add(title);
            Controls.Add(hint);
            Controls.Add(variantBox);
            Controls.Add(installButton);
            Controls.Add(progressBar);
            Controls.Add(statusLabel);
            Shown += async (sender, args) => await LoadManifestAsync();
        }

        private async Task LoadManifestAsync()
        {
            try
            {
                manifest = await Task.Run(() =>
                {
                    using (var client = new WebClient())
                    {
                        client.Headers.Add("User-Agent", "EntokVisionLite-WebSetup");
                        var json = client.DownloadString(WebSetupConfig.ManifestUrl);
                        return new JavaScriptSerializer().Deserialize<ReleaseManifest>(json);
                    }
                });
                if (manifest == null || manifest.variants == null)
                    throw new InvalidDataException("Manifest rilis tidak valid.");
                installButton.Enabled = true;
                statusLabel.Text = "Manifest versi " + manifest.version + " siap.";
            }
            catch (Exception ex)
            {
                statusLabel.Text = "Manifest gagal dimuat: " + ex.Message;
                MessageBox.Show(this, ex.Message, "WebSetup gagal", MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
        }

        private async Task InstallSelectedAsync()
        {
            var key = variantBox.SelectedItem.ToString();
            DownloadVariant variant;
            if (!manifest.variants.TryGetValue(key, out variant) || variant.files == null || variant.files.Count == 0)
            {
                MessageBox.Show(this, "Paket belum tersedia pada manifest.", "WebSetup", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return;
            }
            var totalBytes = 0L;
            foreach (var file in variant.files) totalBytes += file.size;
            var sizeGiB = totalBytes / 1024d / 1024d / 1024d;
            var confirmation = MessageBox.Show(
                this,
                string.Format(CultureInfo.InvariantCulture, "Unduh {0} ({1:0.00} GiB)?", variant.label ?? key, sizeGiB),
                "Konfirmasi unduhan",
                MessageBoxButtons.YesNo,
                MessageBoxIcon.Question);
            if (confirmation != DialogResult.Yes) return;

            installButton.Enabled = false;
            variantBox.Enabled = false;
            try
            {
                var destination = Path.Combine(
                    Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                    "EntokVisionLite", "downloads", manifest.version, key);
                Directory.CreateDirectory(destination);
                string installerPath = null;
                for (var index = 0; index < variant.files.Count; index++)
                {
                    var file = variant.files[index];
                    ValidateManifestFile(file);
                    var currentIndex = index;
                    var progress = new Progress<DownloadProgress>(value =>
                    {
                        progressBar.Value = Math.Max(0, Math.Min(100, value.Percent));
                        statusLabel.Text = string.Format("[{0}/{1}] {2} - {3}%", currentIndex + 1, variant.files.Count, value.FileName, value.Percent);
                    });
                    var completed = await Task.Run(() => DownloadWithResume(file, destination, progress));
                    if (file.installer) installerPath = completed;
                }
                if (string.IsNullOrEmpty(installerPath))
                    throw new InvalidDataException("Manifest tidak menunjuk file installer.");
                statusLabel.Text = "Unduhan terverifikasi. Membuka installer...";
                Process.Start(new ProcessStartInfo(installerPath) { UseShellExecute = true });
                Close();
            }
            catch (Exception ex)
            {
                statusLabel.Text = "Gagal: " + ex.Message;
                MessageBox.Show(this, ex.Message, "WebSetup gagal", MessageBoxButtons.OK, MessageBoxIcon.Error);
                installButton.Enabled = true;
                variantBox.Enabled = true;
            }
        }

        private static void ValidateManifestFile(DownloadFile file)
        {
            if (file == null || string.IsNullOrWhiteSpace(file.name) || Path.GetFileName(file.name) != file.name)
                throw new InvalidDataException("Nama file manifest tidak aman.");
            Uri uri;
            if (!Uri.TryCreate(file.url, UriKind.Absolute, out uri) || uri.Scheme != Uri.UriSchemeHttps)
                throw new InvalidDataException("URL unduhan harus HTTPS.");
            if (file.size <= 0 || string.IsNullOrWhiteSpace(file.sha256))
                throw new InvalidDataException("Ukuran atau SHA-256 file belum tersedia.");
        }

        private static string DownloadWithResume(DownloadFile file, string destination, IProgress<DownloadProgress> progress)
        {
            var finalPath = Path.Combine(destination, file.name);
            if (File.Exists(finalPath) && VerifyFile(finalPath, file)) return finalPath;
            var partialPath = finalPath + ".part";
            Exception lastError = null;
            for (var attempt = 1; attempt <= 4; attempt++)
            {
                try
                {
                    DownloadAttempt(file, partialPath, progress);
                    if (!VerifyFile(partialPath, file))
                    {
                        File.Delete(partialPath);
                        throw new InvalidDataException("SHA-256 atau ukuran unduhan tidak cocok.");
                    }
                    if (File.Exists(finalPath)) File.Delete(finalPath);
                    File.Move(partialPath, finalPath);
                    return finalPath;
                }
                catch (Exception ex)
                {
                    lastError = ex;
                    if (attempt < 4) Thread.Sleep(1000 * attempt * attempt);
                }
            }
            throw new IOException("Unduhan gagal setelah beberapa percobaan.", lastError);
        }

        private static void DownloadAttempt(DownloadFile file, string partialPath, IProgress<DownloadProgress> progress)
        {
            var existing = File.Exists(partialPath) ? new FileInfo(partialPath).Length : 0L;
            if (existing > file.size)
            {
                File.Delete(partialPath);
                existing = 0;
            }
            var request = (HttpWebRequest)WebRequest.Create(file.url);
            request.UserAgent = "EntokVisionLite-WebSetup";
            request.Timeout = 30000;
            request.ReadWriteTimeout = 30000;
            if (existing > 0) request.AddRange(existing);
            using (var response = (HttpWebResponse)request.GetResponse())
            {
                var resumed = existing > 0 && response.StatusCode == HttpStatusCode.PartialContent;
                if (!resumed) existing = 0;
                using (var input = response.GetResponseStream())
                using (var output = new FileStream(
                    partialPath,
                    resumed ? FileMode.Append : FileMode.Create,
                    FileAccess.Write,
                    FileShare.None))
                {
                    var buffer = new byte[1024 * 1024];
                    var received = existing;
                    int count;
                    while ((count = input.Read(buffer, 0, buffer.Length)) > 0)
                    {
                        output.Write(buffer, 0, count);
                        received += count;
                        progress.Report(new DownloadProgress
                        {
                            FileName = file.name,
                            Percent = (int)Math.Min(100, received * 100L / file.size)
                        });
                    }
                }
            }
        }

        private static bool VerifyFile(string path, DownloadFile file)
        {
            if (!File.Exists(path) || new FileInfo(path).Length != file.size) return false;
            using (var stream = File.OpenRead(path))
            using (var sha = SHA256.Create())
            {
                var actual = BitConverter.ToString(sha.ComputeHash(stream)).Replace("-", "").ToLowerInvariant();
                return string.Equals(actual, file.sha256, StringComparison.OrdinalIgnoreCase);
            }
        }
    }

    internal static class Program
    {
        [STAThread]
        private static void Main()
        {
            ServicePointManager.SecurityProtocol = SecurityProtocolType.Tls12;
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Application.Run(new SetupForm());
        }
    }
}
