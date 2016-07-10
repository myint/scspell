check:
	pyflakes scspell.py scspell setup.py
	pycodestyle scspell.py scspell setup.py
	check-manifest
	rstcheck README.rst
	scspell scspell.py setup.py
