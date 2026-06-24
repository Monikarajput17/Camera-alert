"""Run the live camera alert pipeline.

Examples
--------
    python main.py                       # use config.yaml
    python main.py --show                # open a preview window with boxes
    python main.py --source 0            # override the camera source
    python main.py --source test.mp4 --show
"""

import argparse

from cameraalert.pipeline import run


def main():
    parser = argparse.ArgumentParser(description="Camera Alert — face-recognition alarm.")
    parser.add_argument("-c", "--config", default="config.yaml", help="path to config.yaml")
    parser.add_argument("-s", "--source", default=None,
                        help="override camera source (index, RTSP url, or file path)")
    parser.add_argument("--show", action="store_true", help="show an annotated preview window")
    args = parser.parse_args()

    run(config_path=args.config, source_override=args.source, show=args.show)


if __name__ == "__main__":
    main()
