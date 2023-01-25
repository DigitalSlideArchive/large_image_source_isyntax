from girder_large_image.girder_tilesource import GirderTileSource

from . import ISyntaxFileTileSource


class ISyntaxGirderTileSource(ISyntaxFileTileSource, GirderTileSource):
    """
    Provides tile access to Girder items with an ISyntax file.
    """

    cacheName = 'tilesource'
    name = 'isyntax'
