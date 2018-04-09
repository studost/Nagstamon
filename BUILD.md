# How to build Nagstamon


## My builds

* 2017_11_14 Nagstamon-3.1-20171114-mos?
* 2018_03_27 Nagstamon-3.1-20180327-monitos
* 2018_03_29 Nagstamon-3.1-20180329-monitos


### env C:\projects\github\studost\Nagstamon\build

* It works!!!
* with Python3.6


```
python build.py
```

Resulting Installer
C:\projects\github\studost\Nagstamon\build\dist\Nagstamon-3.1-20180327-monitos-win64_setup.exe



### Nagstamon Logfile

C:\Users\ustachowiak\nagstamon.log


## Requirements

* https://nagstamon.ifw-dresden.de/docs/requirements/


If you do not use a binary release of Nagstamon, the following requirements have to be fulfilled:

Python >= 3.4, available at https://www.python.org/downloads/
Several Python modules available via PIP:
beautifulsoup4 – http://www.crummy.com/software/BeautifulSoup/
keyring – https://github.com/jaraco/keyring
lxml – http://lxml.de/
psutil – https://github.com/giampaolo/psutil
pypiwin32 – https://pypi.python.org/pypi/pypiwin32
PyQt5 >= 5.5 – https://riverbankcomputing.com/software/pyqt/
requests – http://docs.python-requests.org/en/latest/
requests-kerberos – https://github.com/requests/requests-kerberos
Linux
All of these are included in any Linux distribution – no PIP required.

For creation of binary packages one might need to install the typical packaging utilities of the choosen distribution to use the included build.py script.

### Windows

* Python 3.6 

If you want to run Nagstamon from sources on Windows, you have to run this PIP command after installing Python. Note that even if there is a newer version right now only PyQt5 5.8 works as excpected:

* C:\python36\scripts\pip install PyQt5==5.8.0 requests requests-kerberos beautifulsoup4 keyring lxml psutil pypiwin32

If you want to create binary packages with the distributed build.py script, you also need

PyInstaller – http://www.pyinstaller.org/
InnoSetup >= 5.5 – http://www.jrsoftware.org/isdl.php
PyInstaller lastest development version which is known to work with Python 3.6 is needed so this one has to be pulled py pip:

* C:\python36\scripts\pip install https://github.com/pyinstaller/pyinstaller/archive/4f3ea16ad788d17b4bb150f9c2c224ab2b82afde.zip


#### Test

* 2017_08_12


```
C:\python36\scripts\pip install PyQt5==5.8.0 requests requests-kerberos beautifulsoup4 keyring psutil pypiwin32
C:\python36\scripts\pip install https://github.com/pyinstaller/pyinstaller/archive/4f3ea16ad788d17b4bb150f9c2c224ab2b82afde.zip
C:\Python36\python.exe pyinstall .\build\build.py
C:\Python36\python.exe pyinstall .\nagstamon.py

```


### macOS

Best experiences are being made with Python 3 and PyQt5 from Homebrew at https://brew.sh. After installing both packages the other dependencies might be retrieved via PIP:

# brew install python3 pyqt5 qt5
# pip3 install beautifulsoup4 keyring lxml psutil requests requests-kerberos setuptools
For binary packages made by the included build.py script you will need PyInstaller too. For macOS the only working version is a development version of pyinstaller:

# pip3 install https://github.com/pyinstaller/pyinstaller/archive/4f3ea16ad788d17b4bb150f9c2c224ab2b82afde.zip
 



