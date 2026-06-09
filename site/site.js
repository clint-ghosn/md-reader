(function () {
  const repo = "clint-ghosn/md-reader";
  const releasePage = `https://github.com/${repo}/releases/latest`;
  const button = document.getElementById("installer-download");
  const status = document.getElementById("release-status");

  function setStatus(text) {
    if (status) {
      status.textContent = text;
    }
  }

  if (!button || !status) {
    return;
  }

  fetch(`https://api.github.com/repos/${repo}/releases/latest`, {
    headers: { Accept: "application/vnd.github+json" },
  })
    .then((response) => {
      if (!response.ok) {
        throw new Error(`GitHub returned ${response.status}`);
      }
      return response.json();
    })
    .then((release) => {
      const assets = Array.isArray(release.assets) ? release.assets : [];
      const installer = assets.find((asset) =>
        /MDReader-v\d+\.\d+\.\d+-windows-x64-setup.*\.exe$/.test(asset.name)
      );

      if (!installer) {
        button.href = release.html_url || releasePage;
        setStatus("Latest release found. Open the release page to choose the installer.");
        return;
      }

      button.href = installer.browser_download_url;
      button.textContent = "Download installer";
      setStatus(`${release.tag_name || "Latest release"} installer: ${installer.name}`);
    })
    .catch(() => {
      button.href = releasePage;
      setStatus("Open the latest release page to download the installer.");
    });
})();
