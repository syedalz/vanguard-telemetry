from asset_node import AssetNode
import threading
import time


def main():
    """Run 10 simulated haul trucks, one thread each, until Ctrl+C."""

    # Shared by every truck; setting it tells them all to stop
    stop_event = threading.Event()
    threads = []

    try:
        # Create truck-01 .. truck-10 and start each in its own thread
        for i in range(1, 11):
            truck = AssetNode(f"truck-{i:02d}", "haul_truck", "localhost", 1883)
            thread = threading.Thread(target=truck.run, args=(stop_event,))
            thread.start()
            threads.append(thread)

        # Keep the main thread alive so it can receive Ctrl+C
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print("Ctrl+C received, shutting down...")
        stop_event.set()
        # Wait for every truck to disconnect before exiting
        for thread in threads:
            thread.join()

if __name__ == '__main__':
    main()
