check:
	pyflakes __main__.py scspell setup.py
	pycodestyle __main__.py scspell setup.py
	check-manifest
	rstcheck README.rst
	python -m scspell --use-builtin-base-dict --relative-to . \
	    --override-dictionary .scspell/dictionary.txt \
	    __main__.py setup.py README.rst scspell/*.py
