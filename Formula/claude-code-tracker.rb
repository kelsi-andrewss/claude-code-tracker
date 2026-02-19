class ClaudeCodeTracker < Formula
  desc "Automatic token, cost, and prompt tracking for Claude Code sessions"
  homepage "https://github.com/kelsi-andrewss/claude-code-tracker"
  url "https://github.com/kelsi-andrewss/claude-code-tracker/archive/refs/tags/v1.1.5.tar.gz"
  sha256 "c936a714228b53b3fd63f123e27fdd0ff619d52f801071158e42397199048ad8"
  license "MIT"

  depends_on "python3"

  def install
    (libexec/"src").install Dir["src/*"]
    libexec.install "install.sh"
    libexec.install "uninstall.sh"
    bin.write_exec_script libexec/"src/cost-summary.py"
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
