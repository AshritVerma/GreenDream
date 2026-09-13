#!/usr/bin/env python3
"""Run GreenDream.  python main.py --open  |  python main.py --demo --open --offline  |  python main.py --display sundai:INSTANCE"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from common.engine import main  # noqa: E402
from app import GreenDream  # noqa: E402

APP = GreenDream

if __name__ == "__main__":
    main(APP)
