import math
import geopandas as gpd
from shapely.geometry import box
from pipeline.ingest.common import utm

def grade_celulas(aoi_geom_4326, tamanho_m=100):
    if tamanho_m <= 0: raise ValueError('tamanho_m deve ser positivo')
    crs = utm(aoi_geom_4326)
    geom = gpd.GeoSeries([aoi_geom_4326],crs=4326).to_crs(crs).iloc[0]
    xmin,ymin,xmax,ymax = geom.bounds
    cells, ids = [], []
    for ix in range(math.floor(xmin/tamanho_m),math.ceil(xmax/tamanho_m)):
        for iy in range(math.floor(ymin/tamanho_m),math.ceil(ymax/tamanho_m)):
            cell = box(ix*tamanho_m,iy*tamanho_m,(ix+1)*tamanho_m,(iy+1)*tamanho_m).intersection(geom)
            if cell.area > 0:
                cells.append(cell); ids.append(f'{crs}_{ix}_{iy}')
    df = gpd.GeoDataFrame({'id':ids},geometry=cells,crs=crs)
    df['area_ha'] = df.area/10000
    return df.to_crs(4326)

def agrega_arvores(celulas, arvores):
    result = celulas.copy()
    result['vol_declarado'] = 0.0; result['n_arvores'] = 0
    if result.empty or arvores.empty: return result
    trees = arvores.to_crs(result.crs)[['geometry','vol_explorado']].reset_index(drop=True)
    trees['_tree'] = trees.index
    joined = gpd.sjoin(trees,result[['geometry']].reset_index(drop=True),predicate='intersects',how='inner')
    # A boundary point belongs to only one deterministic cell.
    joined = joined.sort_values('index_right').drop_duplicates('_tree')
    groups = joined.groupby('index_right').agg(vol_declarado=('vol_explorado',lambda s:s.sum(min_count=1)),n_arvores=('_tree','size'))
    for idx,row in groups.iterrows():
        result.iloc[int(idx),result.columns.get_loc('vol_declarado')] = row.vol_declarado
        result.iloc[int(idx),result.columns.get_loc('n_arvores')] = int(row.n_arvores)
    return result
