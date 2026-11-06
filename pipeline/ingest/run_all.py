import argparse
import pandas as pd
import geopandas as gpd
from .common import OUT
from . import pamgia, if100, poa, inpe, regras_doc, pretriagem

def readme():
    lines = ['# Dados processados AMACRO','', 'Resultados de triagem: indícios para priorizar fiscalização; não constituem prova.', '',
        'Geometrias EPSG:4326. Distâncias e buffers em SIRGAS 2000 / UTM 20S ou 21S. Volumes em m³ e áreas em ha. Datas ISO. Valores desconhecidos permanecem nulos.', '',
        'IF100: apenas produtos Tora, arquivos 2022+, datas de exploração 2022+ (datas ausentes preservadas). Duplicatas exatas removidas. n_arvores conta registros declarados; identificadores podem repetir entre espécies/eventos.', '',
        'PAMGIA: municípios AM Humaitá, Lábrea, Novo Aripuanã, Manicoré, Canutama; RO Porto Velho, Candeias do Jamari. Partes de uma autorização dissolvidas; atributos do registro mais recentemente atualizado.', '',
        'C: distância >20 m. D: soma explorada > volume autorizado; registro explorado >1,1 × autorizado; intensidade >30 m³/ha. E: data fora dos limites inclusivos de validade. Sem árvores não significa ausência de indício.', '',
        'Pré-triagem: C +20, D +25, E +20, DETER +2 por alerta (máximo 20), PRODES ASV/UAS +1 por polígono (máximo 10), janela de exploração ≤90 dias +10. Alertas desde 2021 no buffer de 2 km; proximidade não implica vínculo causal. Top 60 POA e até 20 ASV/UAS elegíveis.', '',
        'Cache por arquivo: use --force após mudanças nos dados ou código para reconstruir dependências. Falha na rede interrompe o processo; não produz camadas vazias como substituição.', '']
    for path in sorted(OUT.glob('*.parquet')):
        df = pd.read_parquet(path)
        lines += [f'## {path.name}',f'{len(df):,} linhas.','', '| Coluna | Tipo |','|---|---|']
        lines += [f'| {col} | {"geometry (EPSG:4326)" if col == "geometry" else dtype} |' for col,dtype in df.dtypes.items()]
        lines += ['']
    path = OUT/'pretriagem.csv'
    if path.exists():
        df = pd.read_csv(path,dtype={'autex':str})
        lines += ['## pretriagem.csv','', '| Coluna | Tipo |','|---|---|'] + [f'| {col} | {dtype} |' for col,dtype in df.dtypes.items()]
    (OUT/'README.md').write_text('\n'.join(lines),encoding='utf-8')

def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--force',action='store_true'); args = parser.parse_args()
    for filename,module in [('autorizacoes.parquet',pamgia),('arvores_if100.parquet',if100),('poa_especies.parquet',poa)]:
        if args.force or not (OUT/filename).exists(): module.run()
        else: print('Cache:',filename,flush=True)
    inpe.run(force=args.force)
    for filename,module in [('regras_doc.parquet',regras_doc),('pretriagem.csv',pretriagem)]:
        if args.force or not (OUT/filename).exists(): module.run()
        else: print('Cache:',filename,flush=True)
    readme()
    print('Autorizacoes:',gpd.read_parquet(OUT/'autorizacoes.parquet').tipo.value_counts().to_dict())
    print('Arvores:',len(pd.read_parquet(OUT/'arvores_if100.parquet')))
    print(pd.read_csv(OUT/'pretriagem.csv',dtype={'autex':str}).head(10).to_string(index=False))

if __name__ == '__main__': main()
