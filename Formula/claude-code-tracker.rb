class ClaudeCodeTracker < Formula
  desc "Automatic token, cost, and prompt tracking for Claude Code sessions"
  homepage "https://github.com/kelsi-andrewss/claude-code-tracker"
  url "https://github.com/kelsi-andrewss/claude-code-tracker/archive/refs/tags/v1.1.7.tar.gz"
  sha256 "3522283689fe3fafb1c1db6ef7c4bb517f3ae13ecbddc87f94a50a011891d5ea"
  license "MIT"

  depends_on "python3"

  def install
    (libexec/"src").install Dir["src/*"]
    libexec.install "install.sh"
    libexec.install "uninstall.sh"
    bin.install "bin/claude-tracker-setup"
    bin.write_exec_script libexec/"src/cost-summary.py"
  end

  def caveats
    <<~EOS
      Run the setup command to register the Claude Code hook:
        claude-tracker-setup

      To view cost summaries:
        claude-tracker-cost

      To uninstall:
        #{libexec}/uninstall.sh
    EOS
  end

  test do
    system "#{bin}/claude-tracker-cost", "--help"
  end
end
