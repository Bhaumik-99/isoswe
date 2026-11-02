import sys
from pathlib import Path

# Add infra/cdk directory to sys.path so modules like environments and stacks can be imported
cdk_root = str(Path(__file__).resolve().parent.parent)
if cdk_root not in sys.path:
    sys.path.insert(0, cdk_root)
