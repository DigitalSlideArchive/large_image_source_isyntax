import io
import math
import os
import threading

import numpy
import PIL.Image
from large_image.cache_util import LruCacheMetaclass, methodcache
from large_image.constants import TILE_FORMAT_NUMPY, SourcePriority
from large_image.exceptions import TileSourceError, TileSourceFileNotFoundError
from large_image.tilesource import FileTileSource

pixelengine = None
softwarerenderbackend = None
softwarerendercontext = None

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
    global pixelengine, softwarerenderbackend, softwarerendercontext

    if pixelengine is None:
        try:
            import pixelengine
            import softwarerenderbackend
            import softwarerendercontext
        except ImportError:
            raise TileSourceError(
                'iSyntax pixelengine, softwarerenderbackend, and/or '
                'softwarerendercontext module not found.')


class ISyntaxFileTileSource(FileTileSource, metaclass=LruCacheMetaclass):
    """
    Provides tile access to nd2 files the nd2 library can read.
    """

    cacheName = 'tilesource'
    name = 'isyntax'
    extensions = {
        None: SourcePriority.LOW,
        'isyntax': SourcePriority.PREFERRED,
    }

    _tileSize = 512

    def __init__(self, path, **kwargs):  # noqa
        """
        Initialize the tile class.  See the base class for other available
        parameters.  See https://gitlab.com/BioimageInformaticsGroup/openphi/
        -/blob/master/openphi/openphi.py for some explanatory code.

        :param path: a filesystem path for the tile source.
        """
        super().__init__(path, **kwargs)

        self._largeImagePath = str(self._getLargeImagePath())
        _lazyImport()
        render_context = softwarerendercontext.SoftwareRenderContext()
        render_backend = softwarerenderbackend.SoftwareRenderBackend()
        # The word "in" seems to be arbitrary
        self._pe = pixelengine.PixelEngine(render_backend, render_context)['in']
        try:
            self._pe.open(self._largeImagePath)
        except RuntimeError:
            if not os.path.isfile(self._largeImagePath):
                raise TileSourceFileNotFoundError(self._largeImagePath) from None
            raise TileSourceError('File cannot be opened via the isyntax source.')
        try:
            self._wsi = self._pe['WSI'].source_view
            self._xidx = self._wsi.dimension_names.index('x')
            self._yidx = self._wsi.dimension_names.index('y')
            self._sidx = self._wsi.dimension_names.index('component')
        except (RuntimeError, ValueError):
            raise TileSourceError(
                'File cannot be opened via the isyntax source: unexpected axes for wsi.')
        self._mm_x = self._mm_y = None
        if self._wsi.dimension_units[self._xidx] == 'MicroMeter':
            self._mm_x = self._wsi.scale[self._xidx] / 1000
        if self._wsi.dimension_units[self._yidx] == 'MicroMeter':
            self._mm_y = self._wsi.scale[self._yidx] / 1000
        self.sizeX = self._wsi.pixel_size[self._xidx]
        self.sizeY = self._wsi.pixel_size[self._yidx]
        if self._wsi.pixel_size[self._sidx] < 1 or self._wsi.pixel_size[self._sidx] > 4:
            raise TileSourceError(
                'File cannot be opened via the isyntax source: unexpected number of components.')
        self.tileWidth = self.tileHeight = self._tileSize
        self.levels = int(max(1, math.ceil(math.log(
            float(max(self.sizeX, self.sizeY)) / self.tileWidth) / math.log(2)) + 1))
        self._levelIdx = [None] * self.levels
        for level in range(self._wsi.num_derived_levels):
            dim = self._wsi.dimension_ranges(level)
            if dim[self._xidx][1] != dim[self._yidx][1]:
                continue
            if dim[self._sidx] != list(range(len(dim[self._sidx]))):
                continue
            idx = int(round(math.log(dim[self._xidx][1]) / math.log(2)))
            if idx < 0 or idx >= self.levels:
                continue
            self._levelIdx[idx] = (level, dim)
        if self._levelIdx[0] is None:
            raise TileSourceError(
                'File cannot be opened via the isyntax source: scale 1 level not located.')
        self._tileLock = threading.RLock()

    def __del__(self):
        if hasattr(self, '_pe'):
            self._pe.close()
            del self._pe

    def getNativeMagnification(self):
        """
        Get the magnification at a particular level.

        :return: magnification, width of a pixel in mm, height of a pixel in mm.
        """
        mm_x = self._mm_x
        mm_y = self._mm_y
        # Estimate the magnification; we don't have a direct value
        mag = 0.01 / mm_x if mm_x else None
        return {
            'magnification': mag,
            'mm_x': mm_x,
            'mm_y': mm_y,
        }

    def getInternalMetadata(self, **kwargs):
        """
        Return additional known metadata about the tile source.  Data returned
        from this method is not guaranteed to be in any particular format or
        have specific values.

        :returns: a dictionary of data or None.
        """
        result = {'isyntax': {}, 'wsi': {}}
        for key in dir(self._pe):
            try:
                if (not key.startswith('_') and
                        not callable(getattr(self._pe, key, None)) and
                        getattr(self._pe, key, None) is not None and
                        key not in {'id', }):
                    result['isyntax'][key] = getattr(self._pe, key, None)
            except Exception:
                pass
        for key in dir(self._wsi):
            if (not key.startswith('_') and
                    not callable(getattr(self._wsi, key, None)) and
                    getattr(self._wsi, key, None) is not None):
                result['wsi'][key] = getattr(self._wsi, key, None)
        return result

    @methodcache()
    def getTile(self, x, y, z, pilImageAllowed=False, numpyAllowed=False, **kwargs):
        self._xyzInRange(x, y, z)
        x0, y0, x1, y1, step = self._xyzToCorners(x, y, z)
        level = self.levels - 1 - z
        scale = 1
        while self._levelIdx[level] is None:
            level -= 1
            scale *= 2
            step /= 2
        x1 -= int(x1 % step)
        y1 -= int(y1 % step)
        x1 = min(x1, self._levelIdx[level][1][self._xidx][2])
        y1 = min(y1, self._levelIdx[level][1][self._yidx][2])
        tile = numpy.empty((int((y1 - y0) / step), int((x1 - x0) / step), 4), dtype=numpy.uint8)
        with self._tileLock:
            region = self._wsi.request_regions(
                region=[[x0, x1 - int(step), y0, y1 - int(step), self._levelIdx[level][0]]],
                data_envelopes=self._wsi.data_envelopes(self._levelIdx[level][0]),
                enable_async_rendering=False,
                background_color=[0, 0, 0, 0],
                buffer_type=pixelengine.PixelEngine.BufferType.RGBA)[0]
            region.get(tile)
            if scale != 1:
                tile = tile[::scale, ::scale, ::]

        return self._outputTile(tile, TILE_FORMAT_NUMPY, x, y, z,
                                pilImageAllowed, numpyAllowed, **kwargs)

    def getAssociatedImagesList(self):
        """
        Return a list of associated images.

        :return: the list of image keys.
        """
        images = []
        for i in range(self._pe.num_images):
            key = self._pe[i].image_type
            if key == 'WSI':
                continue
            if key.endswith('IMAGE') and len(key) > 5:
                key = key[:-5]
            images.append(key.lower())
        return images

    def _getAssociatedImage(self, imageKey):
        """
        Get an associated image in PIL format.

        :param imageKey: the key of the associated image.
        :return: the image in PIL format or None.
        """
        img = None
        for i in range(self._pe.num_images):
            key = self._pe[i].image_type
            if key.lower() == imageKey or key.endswith('IMAGE') and key[:-5].lower() == imageKey:
                img = self._pe[i]
                break
        if img:
            return PIL.Image.open(io.BytesIO(img.image_data))
        return None


def open(*args, **kwargs):
    """
    Create an instance of the module class.
    """
    return ISyntaxFileTileSource(*args, **kwargs)


def canRead(*args, **kwargs):
    """
    Check if an input can be read by the module class.
    """
    return ISyntaxFileTileSource.canRead(*args, **kwargs)
