import argparse, pathlib, os
import PIL.Image

n_x_tiles = 0x10 # Number of tiles in a sprite sheet row

class DataStream:
    '''
        Initialised with a list of data and zero index,
        provides queue-like access to the data and updates index accordingly.
    '''

    class IncompleteDataError(Exception):
        pass

    def __init__(self, data):
        self.data = data
        self.i_data = 0

    def __bool__(self):
        return bool(self.data)
    
    def skip(self, n):
        self.data = self.data[n:]
        self.i_data += n
    
    def skipTo(self, p):
        if p < self.i_data:
            raise RuntimeError(f'Unable to seek backwards to ${p:X} from ${self.i_data:X}')
            
        self.skip(p - self.i_data)

    def peekBytes(self, n):
        if n > len(self.data):
            raise DataStream.IncompleteDataError(f'Unable to read {n} bytes from {len(self.data)} byte buffer (i_data = {self.i_data:X})')

        return self.data[:n]

    def readBytes(self, n):
        ret = self.peekBytes(n)
        self.skip(n)
        return ret

    def peekInt(self, n = 1):
        return int.from_bytes(self.peekBytes(n), 'little')

    def readInt(self, n = 1):
        return int.from_bytes(self.readBytes(n), 'little')
    
    def readStringAscii(self):
        i_null = self.data.index(b'\0')
        ret = self.data[:i_null]
        self.skip(i_null + 1)
        return str(ret, encoding = 'ascii')
    
    def readStringUtf(self):
        i_null = -1
        while i_null % 2 != 0:
            i_null = self.data.index(b'\0\0', i_null + 1)
                
        ret = self.data[:i_null]
        self.skip(i_null + 2)
        return str(ret, encoding = 'utf-16')

class Zspr:
    'Deserialised .zspr binary file'
    
    def __init__(self, filepath):
        with open(filepath, 'rb') as zsprFile:
            zspr = DataStream(zsprFile.read())

        if zspr.readBytes(4) != b'ZSPR':
            raise RuntimeError('ZSPR signature incorrect')

        version = zspr.readInt(1)
        checksum = zspr.readInt(4)
        p_tiles = zspr.readInt(4)
        n_tiles = zspr.readInt(2)
        p_palettes = zspr.readInt(4)
        n_palettes = zspr.readInt(2)
        spriteType = zspr.readInt(2)
        zspr.skip(6) # reserved
        self.spriteName = zspr.readStringUtf()
        self.authorName = zspr.readStringUtf()
        shortAuthorName = zspr.readStringAscii()
        zspr.skipTo(p_tiles)
        tilesBytes = zspr.readBytes(n_tiles)
        zspr.skipTo(p_palettes)
        palettesBytes = zspr.readBytes(n_palettes)
        
        self._initTiles(tilesBytes)
        self._initPalettes(palettesBytes)
    
    def _initTiles(self, tilesBytes):
        def decodePixel(tile, y, x):
            return (
                   tile[y*2]        >> (7 - x) & 1
                | (tile[y*2 + 1]    >> (7 - x) & 1) << 1
                | (tile[y*2 + 0x10] >> (7 - x) & 1) << 2
                | (tile[y*2 + 0x11] >> (7 - x) & 1) << 3
            )
        
        def decodePixelRow(tile, y):
            return [decodePixel(tile, y, x) for x in range(8)]
        
        def decodeTile(tile):
            return [decodePixelRow(tile, y) for y in range(8)]
            
        tilesData = DataStream(tilesBytes)
        self.tiles = []
        while tilesData:
            tile = [tilesData.readInt(1) for _ in range(0x20)]
            self.tiles += [decodeTile(tile)]
    
    def _initPalettes(self, palettesBytes):
        def toRgb(bgr):
            return ((bgr & 0x1F) * 0xFF // 0x1F, (bgr >> 5 & 0x1F) * 0xFF // 0x1F, (bgr >> 10 & 0x1F) * 0xFF // 0x1F)
            
        palettesData = DataStream(palettesBytes)
        
        self.palettes = []
        for _ in range(4):
            paletteBgr = [palettesData.readInt(2) for _ in range(0xF)]
            paletteRgb = [toRgb(colour) for colour in paletteBgr]
            self.palettes += [[None] + paletteRgb]
        
        coloursBgr = [palettesData.readInt(2) for _ in range(2)]
        coloursRgb = [toRgb(colour) for colour in coloursBgr]

def drawTile(palette, tile, positionX, positionY):
    for y_pixel in range(8):
        for x_pixel in range(8):
            x = positionX + x_pixel
            y = positionY + y_pixel
            i_colour = tile[y_pixel][x_pixel]
            if i_colour != 0:
                colour = palette[i_colour]
                pixels[x, y] = colour

def drawMetatile(palette, tiles, x_metatile, y_metatile, positionX, positionY):
    for y_tile in range(2):
        for x_tile in range(2):
            i_tile = (y_metatile * 2 + y_tile) * n_x_tiles + x_metatile * 2 + x_tile
            drawTile(palette, tiles[i_tile], positionX + x_tile * 8, positionY + y_tile * 8)

argparser = argparse.ArgumentParser(description = 'Export preview of sprites from ZSPR files.')
argparser.add_argument('zsprs_path', type = pathlib.Path, help = 'Path to directory containing .zspr files')
args = argparser.parse_args()

if not os.path.exists('images'):
    os.mkdir('images')
    
with open('index.html', 'w') as html:
    html.write('<html>\n')
    html.write('<head>\n')
    html.write('<link rel=stylesheet href=index.css>\n')
    html.write('</head>\n')
    html.write('<body>\n')
    
    for zspr_path in args.zsprs_path.glob('*.zspr'):
        zspr = Zspr(zspr_path)
        print(zspr_path.name)
        html.write('<span class=spriteBox>\n')
        html.write(f'<div>{zspr.spriteName}<br>by {zspr.authorName}</div>')

        # Load facing down metatile
        for i_palette in range(3):
            variant = ['green', 'blue', 'red'][i_palette]
            imagePath = f'images/{zspr_path.stem} - {variant} mail.png'
            print(imagePath)
            
            img = PIL.Image.new('RGB', (16, 24), color = 'black')
            pixels = img.load()
            drawMetatile(zspr.palettes[i_palette], zspr.tiles, 3, 1, 0, 8)
            drawMetatile(zspr.palettes[i_palette], zspr.tiles, 1, 0, 0, 0)
            img = img.resize((16 * 4, 24 * 4), PIL.Image.Resampling.NEAREST)
            img.save(imagePath)
            
            html.write(f'<img src="{imagePath}"></img>\n')

        # Load facing down bunny metatile
        imagePath = f'images/{zspr_path.stem} - bunny.png'
        
        img = PIL.Image.new('RGB', (16, 24), color = 'black')
        pixels = img.load()
        drawMetatile(zspr.palettes[3], zspr.tiles, 0, 0x1A, 0, 8)
        drawMetatile(zspr.palettes[3], zspr.tiles, 5, 0x19, 0, 0)
        img = img.resize((16 * 4, 24 * 4), PIL.Image.Resampling.NEAREST)
        img.save(imagePath)
        
        html.write(f'<img src="{imagePath}"></img>\n')
        html.write('</span>\n')
    
    html.write('</body>\n')
    html.write('</html>\n')


'''
# Load all tiles
n_y_tiles = len(zspr.tiles) // n_x_tiles
for i_palette in range(4):
    img = PIL.Image.new('RGB', (n_x_tiles * 8, n_y_tiles * 8), color = 'black')
    pixels = img.load()
    for y_tile in range(n_y_tiles):
        for x_tile in range(n_x_tiles):
            drawTile(zspr.palettes[i_palette], zspr.tiles[y_tile * n_x_tiles + x_tile], x_tile * 8, y_tile * 8)

    img = img.resize((n_x_tiles * 8 * 4, n_y_tiles * 8 * 4), PIL.Image.Resampling.NEAREST)
    variant = ['green mail', 'blue mail', 'red mail', 'bunny'][i_palette]
    img.save(f'tiles - {zspr.spriteName} - {variant}.png')
'''
