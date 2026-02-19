class ClaudeCodeTracker < Formula
  desc "Automatic token, cost, and prompt tracking for Claude Code sessions"
  homepage "https://github.com/kelsi-andrewss/claude-code-tracker"
  url "https://github.com/kelsi-andrewss/claude-code-tracker/archive/refs/tags/v1.0.0.tar.gz"
  sha256 "25060fb45605d90f5c08eb0d1fb949a6717349c333397d0bf1f9f4ca642cd9e3"
  license "MIT"

  depends_on "python3"

  def install
    libexec.install Dir["src/*"]
    libexec.install "install.sh"
    libexec.install "uninstall.sh"
    bin.write_exec_script libexec/"cost-summary.py"
  end

  def post_install
    system "#{libexec}/install.sh"
  end

  def caveats
    <<~EOS
      claude-code-tracker has been installed and the Stop hook registered.
      Restart Claude Code to activate session tracking.

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
