class ClaudeCodeTracker < Formula
  desc "Automatic token, cost, and prompt tracking for Claude Code sessions"
  homepage "https://github.com/kelsi-andrewss/claude-code-tracker"
  url "https://github.com/kelsi-andrewss/claude-code-tracker/archive/refs/tags/v1.1.0.tar.gz"
  sha256 "fb4e82a77b0b1e4c6055de4057d04d4783a7391706f2ae06f7a42df087b4554f"
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
