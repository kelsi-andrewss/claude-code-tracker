class ClaudeCodeTracker < Formula
  desc "Automatic token, cost, and prompt tracking for Claude Code sessions"
  homepage "https://github.com/kelsi-andrewss/claude-code-tracker"
  url "https://github.com/kelsi-andrewss/claude-code-tracker/archive/refs/tags/v1.1.3.tar.gz"
  sha256 "c3e5676349363dba20ce284714b090a7e983f4d7378bf22d54a45ab691841f04"
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
