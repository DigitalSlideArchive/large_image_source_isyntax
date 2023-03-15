import os

from large_image.cache_util import LruCacheMetaclass, strhash
from large_image.exceptions import TileSourceError, TileSourceFileNotFoundError
from large_image.tilesource import FileTileSource

rpyc = None

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _importlib_version

try:
    __version__ = _importlib_version(__name__)
except PackageNotFoundError:
    # package is not installed
    pass


def _lazyImport():
    """
    Import the nd2 module.  This is done when needed rather than in the module
    initialization because it is slow.
    """
    global rpyc

    if rpyc is None:
        try:
            import rpyc
        except ImportError:
            raise TileSourceError('rpycs module not found.')


class RPYCFileTileSource(FileTileSource, metaclass=LruCacheMetaclass):
    """
    Provides tile access to nd2 files the nd2 library can read.
    """

    cacheName = 'tilesource'
    name = 'rpyc'

    def __init__(self, path, **kwargs):
        """
        Initialize the tile class, defering to the remote server.

        :param path: a filesystem path for the tile source.
        """
        super().__init__(path, **kwargs)
        self._spec = kwargs.copy()
        self._spec.pop('style', None)
        self._largeImagePath = str(self._getLargeImagePath())
        _lazyImport()
        try:
            conn = rpyc.classic.connect('localhost')
        except Exception:
            raise TileSourceError(
                'File cannot be opened via the rpyc source: failed to connect to an rpyc server')
        if not os.path.isfile(self._largeImagePath):
            raise TileSourceFileNotFoundError(self._largeImagePath) from None
        try:
            self._proxy = conn.modules.large_image.open(self._largeImagePath, **kwargs)
        except Exception:
            raise TileSourceError('File cannot be opened via the rpyc source.')
        for key in dir(self._proxy):
            if not key.startswith('__') and key not in {
                '_classkey', '_unstyledClassKey', 'cache', 'cacheName',
                'cache_lock', 'logger', 'wrapKey', '_tileIterator',
                'tileIterator', 'tileIteratorAtAnotherScale', 'getSingleTile',
                'getSingleTileAtAnotherScale', 'getTileCount', 'histogram',
                'getRegion', 'tileFrames', 'getPixel',
            }:
                try:
                    setattr(self, key, getattr(self._proxy, key))
                    if callable(getattr(self._proxy, key)):
                        def wrap(key):
                            def wrapped_method(*args, **kwargs):
                                result = rpyc.utils.classic.obtain(
                                    getattr(self._proxy, key)(*args, **kwargs))
                                return result
                            return wrapped_method
                        setattr(self, key, wrap(key))
                except Exception:
                    pass

    @staticmethod
    def getLRUHash(*args, **kwargs):
        kwargs = kwargs.copy()
        kwargs.pop('style', None)
        return strhash(
            super(RPYCFileTileSource, RPYCFileTileSource).getLRUHash(
                *args, **kwargs),
            kwargs,
        )

    def getState(self):
        return super().getState() + ',' + repr(self._spec)


def open(*args, **kwargs):
    """
    Create an instance of the module class.
    """
    return RPYCFileTileSource(*args, **kwargs)


def canRead(*args, **kwargs):
    """
    Check if an input can be read by the module class.
    """
    return RPYCFileTileSource.canRead(*args, **kwargs)
