from girder_large_image.girder_tilesource import GirderTileSource

from . import RPYCFileTileSource


class RPYCGirderTileSource(RPYCFileTileSource, GirderTileSource):
    """
    Provides tile access to Girder items with an RPYC file.
    """

    cacheName = 'tilesource'
    name = 'rpyc'

    # This doesn't work properly, and requires more investigation to determine
    # why using a fuse path causes failure
    # _mayHaveAdjacentFiles = True
