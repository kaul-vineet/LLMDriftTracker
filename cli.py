"""
drift — command-line interface for LLM Drift Tracker

  drift setup        run the setup wizard (bootstrap)
  drift run          start the autonomous polling agent
  drift dashboard    launch the Streamlit read-only dashboard
"""
import argparse, os, subprocess, sys

CMDS = {
    "setup":     "run the setup wizard",
    "run":       "start the autonomous polling agent",
    "dashboard": "launch the Streamlit dashboard",
}

def _banner():
    c, r = "\033[96m\033[1m", "\033[0m"
    print(f"\n  {c}⚡ LLM Drift Tracker{r}  —  drift <command>\n")
    print(f"  {'Command':<14}  Description")
    print(f"  {'─' * 12}  {'─' * 36}")
    for cmd, desc in CMDS.items():
        print(f"  {c}{cmd:<14}{r}  {desc}")
    print()


def main():
    parser = argparse.ArgumentParser(
        prog="drift",
        description="LLM Drift Tracker CLI",
        add_help=False,
    )
    parser.add_argument("command", nargs="?", choices=list(CMDS), metavar="command")
    parser.add_argument("-h", "--help", action="store_true")
    args, _ = parser.parse_known_args()

    if args.help or not args.command:
        _banner()
        return

    root = os.path.dirname(os.path.abspath(__file__))

    if args.command == "setup":
        sys.path.insert(0, root)
        import bootstrap
        bootstrap.main()

    elif args.command == "run":
        sys.path.insert(0, root)
        from agent.main import main as agent_main
        agent_main()

    elif args.command == "dashboard":
        app = os.path.join(root, "dashboard", "app.py")
        subprocess.run([sys.executable, "-m", "streamlit", "run", app], check=True)


if __name__ == "__main__":
    main()
