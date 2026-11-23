"""python3 -m nefes_baslat <komut> … — bkz. nefes_baslat/__init__.py."""
import sys

from nefes_baslat import main

sys.exit(main(sys.argv[1:]))
