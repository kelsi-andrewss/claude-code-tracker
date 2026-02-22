class ClaudeCodeTracker < Formula
  desc "Automatic token, cost, and prompt tracking for Claude Code sessions"
  homepage "https://github.com/kelsi-andrewss/claude-code-tracker"
  url "https://github.com/kelsi-andrewss/claude-code-tracker/archive/refs/tags/v1.2.3.tar.gz"
  sha256 "c9aa2cbfc4542e997d49aa90c95372c8ed5c7a5db984187e45323e72e439238d"
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
