check:
	pyflakes scspell.py scspell setup.py
	pycodestyle scspell.py scspell setup.py
	check-manifest
	rstcheck README.rst
	./scspell.py --use-builtin-base-dict \
	    --override-dictionary .scspell/dictionary.txt \
	    scspell.py setup.py README.rst
