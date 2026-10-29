"""Opt-in language compatibility track, kept separate from frozen V1 transfer."""
import bench
from protocol_v2 import ProtocolV2

if __name__ == '__main__':
    bench.Protocol = ProtocolV2
    bench.main()
