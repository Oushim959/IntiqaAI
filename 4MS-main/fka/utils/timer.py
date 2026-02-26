import time

class ResponseTimer:
    def __init__(self):
        self.start_time = None
    
    def start(self):
        """Start the response timer"""
        print("\n⏱️  Response timer started...")
        print("   Press Enter when you start typing, then press Enter twice when finished.")
        input("   Press Enter to begin...")
        self.start_time = time.time()
        return self.start_time
    
    def stop(self) -> float:
        """Stop timer and return duration in minutes"""
        if self.start_time is None:
            return 0.0
        
        duration = time.time() - self.start_time
        self.start_time = None # Reset
        return duration / 60  # Convert to minutes
    
    def get_elapsed_time(self) -> float:
        """Get current elapsed time without stopping"""
        if self.start_time is None:
            return 0.0
        return (time.time() - self.start_time) / 60
