"""
Pytest configuration and custom reporting hooks.
Generates the tabular gateway validation summary in the terminal.
"""
# ==============================================================================
# CUSTOM TERMINAL REPORT
# ==============================================================================
def pytest_terminal_summary(terminalreporter):
    """Generates a clean list of failed IDs at the very end of the run."""
    stats = terminalreporter.stats

    print("\n" + "=" * 60)

    if "failed" in stats:
        num_fails = len(stats["failed"])
        # Use .get() to check for passes in case zero tests passed
        num_successes = len(stats.get("passed", []))
        print(f" GATEWAY TEST SUMMARY ({num_fails} FAILED & {num_successes} PASSED) ")
        print("=" * 60)
        for test in stats["failed"]:
            if "[" in test.nodeid:
                tx_rx_arb = test.nodeid.split("[")[-1].rstrip("]")
                print(f" - {tx_rx_arb}")
            else:
                print(f" - {test.nodeid}")
    elif "passed" in stats:
        num_passes = len(stats["passed"])
        print(f" GATEWAY TEST SUMMARY (100% SUCCESS - {num_passes} ROUTES VERIFIED) ")
    print("=" * 60)
