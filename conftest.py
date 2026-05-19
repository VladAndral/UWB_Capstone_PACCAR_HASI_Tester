# ==============================================================================
# CUSTOM TERMINAL REPORT
# ==============================================================================

def pytest_terminal_summary(terminalreporter, exitstatus, config):
    """Generates a clean list of failed IDs at the very end of the run."""
    stats = terminalreporter.stats

    print(f"\n" + "="*60)
    
    if 'failed' in stats:
        numFails = len(stats['failed']) if 'failed' in stats else 0
        numSuccesses = len(stats['passed']) if 'passed' in stats else 0
        print(f" GATEWAY TEST SUMMARY ({numFails} FAILED & {numSuccesses} PASSED) ")
        print(f"="*60)
        for test in stats['failed']:
            if '[' in test.nodeid:
                tx_rx_arb = test.nodeid.split('[')[-1].rstrip(']')
                print(f" - {tx_rx_arb}")
            else:
                print(f" - {test.nodeid}")
                
    elif 'passed' in stats:
        numPasses = len(stats['passed'])
        print(f" GATEWAY TEST SUMMARY (100% SUCCESS - {numPasses} ROUTES VERIFIED) ")
        
    print(f"="*60)