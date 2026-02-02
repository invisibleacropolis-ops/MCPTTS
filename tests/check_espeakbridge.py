try:
    from piper import espeakbridge
    print(f"Successfully imported espeakbridge: {espeakbridge}")
except ImportError as e:
    print(f"Failed to import espeakbridge: {e}")
except Exception as e:
    print(f"An error occurred: {e}")

try:
    import piper.espeakbridge
    print(f"Successfully imported piper.espeakbridge: {piper.espeakbridge}")
except ImportError as e:
    print(f"Failed to import piper.espeakbridge: {e}")
