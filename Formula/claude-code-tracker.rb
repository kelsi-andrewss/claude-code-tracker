class ClaudeCodeTracker < Formula
  desc "Automatic token, cost, and prompt tracking for Claude Code sessions"
  homepage "https://github.com/kelsi-andrewss/claude-code-tracker"
  url "https://github.com/kelsi-andrewss/claude-code-tracker/archive/refs/tags/v1.1.7.tar.gz"
  sha256 "ec927840ffdca85d4a581609eee59a1509d839938c6f1faf7f73282e97ca2b77"
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
