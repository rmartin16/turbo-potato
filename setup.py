from setuptools import setup, find_packages

setup(
    name='turbo-potato',
    version='0.0.0',
    packages=find_packages(exclude=['*.tests', '*.tests.*', 'tests.*', 'tests', 'scripts']),
    include_package_data=True,
    install_requires=['unidecode',
                      'PyInquirer',
                      'parse-torrent-title',
                      'requests',
                      'tvdbsimple',
                      'tmdbsimple',
                      'urwid',
                      'qbittorrent-api',
                      'nltk'],
    entry_points={'console_scripts': ['turbopotato = turbopotato.__main__:main']},
    url='https://github.com/rmartin16/turbo-potato',
    author='Russell Martin',
    description='Media torrent manager',
    zip_safe=False,
    license='MIT',
    classifiers=['Programming Language :: Python :: 3.8',
                 'Programming Language :: Python :: 3.7',
                 'Programming Language :: Python :: 3.6']
)
