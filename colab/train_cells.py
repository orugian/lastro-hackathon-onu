# %% Treino: Prithvi via TerraTorch, fallback U-Net siamesa
import gc
import torch
from torch import nn
from torch.nn import functional as F
from torch.utils.data import Dataset, DataLoader
from sklearn.metrics import confusion_matrix
from skimage.filters import threshold_otsu
import matplotlib.pyplot as plt

torch.manual_seed(SEED)
torch.cuda.manual_seed_all(SEED)
torch.backends.cudnn.benchmark = False
torch.backends.cudnn.deterministic = True
DEVICE = 'cuda' if torch.cuda.is_available() else 'cpu'
if DEVICE != 'cuda':
    raise RuntimeError('Ative GPU em Ambiente de execução > Alterar tipo de ambiente e execute novamente.')
GPU_GB = torch.cuda.get_device_properties(0).total_memory / 1024**3
print('GPU:',torch.cuda.get_device_name(0),round(GPU_GB,1),'GB')

# Estatísticas publicadas pelo Prithvi-EO-2.0 para reflectância HLS.
MEAN = np.array([.1087,.1342,.1433,.2734,.1958,.1363],np.float32)
STD = np.array([.2248,.2179,.2178,.1850,.1242,.1049],np.float32)
CONFIG.update(normalization_mean=MEAN.tolist(),normalization_std=STD.tolist(),
              nir_proxy='B8 (10 m), em lugar de NIR narrow HLS; domain shift',gpu=torch.cuda.get_device_name(0))

class Chips(Dataset):
    def __init__(self, subset):
        self.rows = [r for r in records if r['split']==subset]
    def __len__(self):
        return len(self.rows)
    def __getitem__(self,i):
        with np.load(self.rows[i]['path']) as z:
            x,y,valid = z['x'].copy(),z['y'].copy(),z['valid'].copy()
            observed = z['observed'].copy()
        x = (x-np.tile(MEAN,2)[:,None,None])/np.tile(STD,2)[:,None,None]
        x[:,~observed] = 0
        return torch.from_numpy(x),torch.from_numpy(y).float(),torch.from_numpy(valid)

datasets = {s:Chips(s) for s in ['train','val','test']}

class PrithviSegmenter(nn.Module):
    """Backbone TerraTorch multitemporal + decoder convolucional de dois frames."""
    def __init__(self, variant):
        super().__init__()
        from terratorch.registry import BACKBONE_REGISTRY
        self.backbone = BACKBONE_REGISTRY.build(
            variant, pretrained=True, num_frames=2,
            bands=['BLUE','GREEN','RED','NIR_NARROW','SWIR_1','SWIR_2'])
        # out_channels inclui o número de frames no registro TerraTorch.
        channels = self.backbone.out_channels[-1]
        self.decoder = nn.Sequential(nn.Conv2d(channels,128,1),nn.GroupNorm(8,128),nn.GELU(),
                                     nn.Conv2d(128,64,3,padding=1),nn.GELU(),nn.Conv2d(64,1,1))
        # Fine-tune dos últimos 2/4 blocos e decoder reduz memória e tempo na T4.
        for p in self.backbone.parameters():
            p.requires_grad = False
        blocks = getattr(self.backbone,'blocks',None)
        if blocks is None:
            blocks = getattr(getattr(self.backbone,'encoder',None),'blocks',None)
        if blocks is None:
            raise RuntimeError('Backbone sem blocks acessíveis para fine-tuning parcial.')
        for block in blocks[-(2 if MODO_RAPIDO else 4):]:
            for p in block.parameters():
                p.requires_grad = True
    def forward(self,x):
        # CHW concatenado -> B,C,T,H,W (não B,T,C,H,W).
        t = x.reshape(x.shape[0],2,6,*x.shape[-2:]).transpose(1,2)
        features = self.backbone(t)[-1]
        h = x.shape[-2]//16
        if features.ndim != 3:
            raise RuntimeError(f'Formato inesperado do backbone: {features.shape}')
        if features.shape[1] == 2*h*h+1:
            features = features[:,1:]
        if features.shape[1] != 2*h*h:
            raise RuntimeError(f'Tokens temporais inesperados: {features.shape}')
        features = features.reshape(x.shape[0],2,h,h,-1).permute(0,1,4,2,3).flatten(1,2)
        return F.interpolate(self.decoder(features),size=x.shape[-2:],mode='bilinear',align_corners=False)[:,0]

class SiameseUNet(nn.Module):
    """Dois ramos de seis bandas, ResNet34 compartilhada e fusão pré/pós."""
    def __init__(self):
        super().__init__()
        import segmentation_models_pytorch as smp
        self.net = smp.Unet(encoder_name='resnet34',encoder_weights='imagenet',in_channels=6,classes=1)
        self.fuse = nn.ModuleList([nn.Conv2d(2*c,c,1) for c in self.net.encoder.out_channels])
    def forward(self,x):
        a,b = self.net.encoder(x[:,:6]),self.net.encoder(x[:,6:])
        fused = [layer(torch.cat([p,q],1)) for layer,p,q in zip(self.fuse,a,b)]
        return self.net.segmentation_head(self.net.decoder(fused))[:,0]

def loss_fn(logits,y,valid):
    if not valid.any():
        return logits.sum()*0
    bce = F.binary_cross_entropy_with_logits(logits[valid],y[valid])
    p,t = logits.sigmoid()[valid],y[valid]
    dice = 1-(2*(p*t).sum()+1)/(p.sum()+t.sum()+1)
    return bce+dice

def fit(model,batch):
    model = model.to(DEVICE)
    loaders = {s:DataLoader(ds,batch_size=batch,shuffle=(s=='train'),num_workers=0,
                           generator=torch.Generator().manual_seed(SEED)) for s,ds in datasets.items()}
    optimizer = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad],lr=1e-4,weight_decay=.01)
    scaler = torch.amp.GradScaler('cuda')
    best, stale, log = float('inf'),0,[]
    for epoch in range(EPOCAS):
        losses = {}
        for subset in ['train','val']:
            model.train(subset=='train')
            total = count = 0
            for x,y,valid in loaders[subset]:
                x,y,valid = x.to(DEVICE),y.to(DEVICE),valid.to(DEVICE)
                optimizer.zero_grad(set_to_none=True)
                with torch.set_grad_enabled(subset=='train'),torch.autocast('cuda',dtype=torch.float16):
                    logits = model(x)
                    loss = loss_fn(logits,y,valid)
                if not torch.isfinite(loss):
                    raise RuntimeError('Loss não finita; interrompido para evitar métricas inválidas.')
                if subset=='train':
                    scaler.scale(loss).backward()
                    scaler.unscale_(optimizer)
                    torch.nn.utils.clip_grad_norm_(model.parameters(),1)
                    scaler.step(optimizer)
                    scaler.update()
                total += loss.item()*len(x)
                count += len(x)
            losses[subset] = total/count
        log.append(dict(epoch=epoch+1,**losses))
        print(f'Época {epoch+1}/{EPOCAS}: {losses}',flush=True)
        if losses['val'] < best-1e-4:
            best,stale = losses['val'],0
            torch.save(model.state_dict(),ROOT/'lastro_best.pt')
        else:
            stale += 1
        if stale >= 3:
            print('Early stopping (paciência 3).')
            break
    model.load_state_dict(torch.load(ROOT/'lastro_best.pt',map_location=DEVICE,weights_only=True))
    return model.eval(),log

attempts = []
variants = ['prithvi_eo_v2_100_tl'] if GPU_GB<20 else ['prithvi_eo_v2_300_tl','prithvi_eo_v2_100_tl']
variants += ['unet-siamesa']
model = None
for variant in variants:
    try:
        print('Tentando',variant,flush=True)
        torch.manual_seed(SEED)
        model = SiameseUNet() if variant=='unet-siamesa' else PrithviSegmenter(variant)
        model,train_log = fit(model,batch=4 if variant=='unet-siamesa' else 2)
        MODEL_NAME = 'unet-siamesa' if variant=='unet-siamesa' else 'prithvi-eo-2.0'
        break
    except Exception as exc:
        attempts.append(dict(model=variant,error=f'{type(exc).__name__}: {exc}'))
        print('Fallback:',attempts[-1],flush=True)
        del model
        model = None
        gc.collect()
        torch.cuda.empty_cache()
if model is None:
    raise RuntimeError(f'Nenhum modelo treinou: {attempts}')
CONFIG.update(modelo=MODEL_NAME,variant=variant,fallbacks=attempts,
              epocas_executadas=len(train_log),treino=train_log,lr=1e-4,
              fine_tune='últimos 2/4 blocos Prithvi ou encoder completo ResNet34',early_stopping_patience=3)

# %% Avaliação e comparadores nos mesmos pixels
def metrics(cm):
    tn,fp,fn,tp = map(int,cm.ravel())
    ratio = lambda a,b: a/b if b else 0.0
    return dict(iou=ratio(tp,tp+fp+fn),f1=ratio(2*tp,2*tp+fp+fn),
                precisao=ratio(tp,tp+fp),recall=ratio(tp,tp+fn),
                matriz_confusao=cm.tolist(),n_pixels_teste=int(cm.sum()))

@torch.inference_mode()
def predict_array(x,valid):
    normalized = (x-np.tile(MEAN,2)[:,None,None])/np.tile(STD,2)[:,None,None]
    normalized[:,~valid] = 0
    with torch.autocast('cuda',dtype=torch.float16):
        prob = model(torch.from_numpy(normalized[None]).to(DEVICE)).sigmoid()[0].float().cpu().numpy()
    return prob

def delta_ndvi(x):
    return ndvi(x)-ndvi(x,6)  # positivo = perda de vigor

def lgb_features(x):
    indices = []
    for offset in (0,6):
        nir = x[offset+3]
        indices.append(np.stack([ndvi(x,offset),
                                 (nir-x[offset+5])/(nir+x[offset+5]+1e-6),
                                 (nir-x[offset+4])/(nir+x[offset+4]+1e-6)]))
    return np.concatenate([x,*indices,indices[0]-indices[1]],axis=0).transpose(1,2,0)

def sample_pixels(subset,max_per_chip=1000):
    xs,ys,ds = [],[],[]
    rng = np.random.default_rng(SEED)
    for r in records:
        if r['split'] != subset:
            continue
        with np.load(r['path']) as z:
            ids = np.flatnonzero(z['valid'])
            ids = rng.choice(ids,size=min(len(ids),max_per_chip),replace=False)
            xs.append(lgb_features(z['x']).reshape(-1,21)[ids])
            ys.append(z['y'].ravel()[ids])
            ds.append(delta_ndvi(z['x']).ravel()[ids])
    return np.concatenate(xs),np.concatenate(ys),np.concatenate(ds)

import lightgbm as lgb
xt,yt,dt = sample_pixels('train')
xv,yv,_ = sample_pixels('val')
otsu = max(0.,float(threshold_otsu(dt)))  # limiar aprendido apenas no treino
lgbm = lgb.LGBMClassifier(n_estimators=350,num_leaves=31,learning_rate=.05,
                          random_state=SEED,n_jobs=2,verbosity=-1,deterministic=True,force_col_wise=True)
lgbm.fit(xt,yt,eval_set=[(xv,yv)],callbacks=[lgb.early_stopping(25,verbose=False)])
pv = lgbm.predict_proba(xv)[:,1]
thresholds = np.arange(.1,.91,.05)
lgb_threshold = float(max(thresholds,key=lambda t:metrics(confusion_matrix(yv,pv>=t,labels=[0,1]))['f1']))
lgbm.booster_.save_model(str(OUT/'lgbm_mesmos_chips.txt'))
cms = {key:np.zeros((2,2),dtype=np.int64) for key in ['dl','baseline','lightgbm']}
examples = 0
for r in records:
    if r['split']!='test':
        continue
    with np.load(r['path']) as z:
        x,y,valid = z['x'],z['y'],z['valid']
        prob = predict_array(x,z['observed'])
        base = delta_ndvi(x)>otsu
        # Inferir só pixels observáveis, em lotes pequenos.
        features = lgb_features(x)[valid]
        plgb = lgbm.predict_proba(features)[:,1]>=lgb_threshold
        for key,p in [('dl',prob[valid]>=.5),('baseline',base[valid]),('lightgbm',plgb)]:
            cms[key] += confusion_matrix(y[valid],p,labels=[0,1])
        if examples<4:
            fig,axs = plt.subplots(1,4,figsize=(14,4))
            panels = [np.clip(x[[2,1,0]].transpose(1,2,0)/.3,0,1),
                      np.clip(x[[8,7,6]].transpose(1,2,0)/.3,0,1),
                      np.where(valid,y,np.nan),np.where(valid,prob,np.nan)]
            for ax,p,title in zip(axs,panels,['Pré','Pós','Rótulo (vazio = ignorado)','Probabilidade']):
                ax.imshow(p,vmin=0,vmax=1)
                ax.set_title(title)
                ax.axis('off')
            fig.suptitle(f"Teste espacial: {r['bloco']} / {r['year']}")
            fig.tight_layout()
            fig.savefig(OUT/f'exemplo_{examples+1}.png',dpi=140)
            plt.close(fig)
            examples += 1
PROTOCOL = ('Blocos UTM SIRGAS2000 de 25 km, seed 42, 70/15/15 por bloco; '
            'todos os anos de um bloco no mesmo split; chips inteiros dentro do bloco; '
            'AOIs de demonstração excluídas. Métricas de pixel apenas no teste espacial. '
            'Pixels sem observação e negativos sem NDVI pré > 0,75 ou com histórico de alertas ignorados. '
            'DL limiar fixo 0,5; Otsu ajustado no treino; LightGBM limiar ajustado na validação. '
            'Matriz [[TN,FP],[FN,TP]]. Amostragem enriquecida em positivos, não estima prevalência regional.')
OBS = ['Resultados experimentais: indícios para priorizar fiscalização; não constituem prova.',
       'PRODES/DETER não captam todas as pequenas clareiras; ausência de rótulo não garante floresta intacta.',
       'PRODES usa ano de monitoramento e DETER out/set; mediana jun/set pode diluir mudanças e não coincide exatamente com eventos.',
       'Proxy B8 para NIR narrow HLS e resolução 10 m implicam mudança de domínio do Prithvi.',
       'LightGBM abaixo é refeito nestes chips; métricas do detector local com 5 folds/5 km não são diretamente comparáveis.',
       'Tempos de 30 min/2 h são metas, dependem da GPU, rede, WFS, GEE e quantidade de nuvens.']
report = dict(nome=MODEL_NAME,**metrics(cms['dl']),obs=OBS,protocolo=PROTOCOL,
              baseline_mesmos_chips=dict(nome='delta-NDVI + Otsu',threshold=otsu,**metrics(cms['baseline'])),
              lightgbm_mesmos_chips=dict(nome='lightgbm',threshold=lgb_threshold,**metrics(cms['lightgbm'])))
(OUT/'metrics_dl.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
CONFIG.update(otsu_threshold=otsu,lgbm_threshold=lgb_threshold,lgbm_features=21,
              lgbm_params=lgbm.get_params(),protocolo=PROTOCOL)
print(json.dumps(report,indent=2,ensure_ascii=False))

# %% AOIs: GeoTIFF em grade UTM, janelas sobrepostas e pesos nas bordas
from rasterio.windows import Window

def window_starts(length,step=168):
    if length<=SIZE:
        return [0]
    return sorted(set(list(range(0,length-SIZE+1,step))+[length-SIZE]))

def infer_aoi(aoi):
    epsg = utm_epsg((aoi['bbox'][0]+aoi['bbox'][2])/2)
    geometry = geom_transform(Transformer.from_crs(4326,epsg,always_xy=True).transform,box(*aoi['bbox']))
    xmin,ymin,xmax,ymax = geometry.bounds
    left,top = math.floor(xmin/RES)*RES,math.ceil(ymax/RES)*RES
    width,height = math.ceil((xmax-left)/RES),math.ceil((top-ymin)/RES)
    if width*height>100_000_000:
        raise ValueError('AOI maior que 100 milhões de pixels: dividir a AOI em partes.')
    affine = from_origin(left,top,RES,RES)
    image = stack_image(aoi['pre'],aoi['pos'],ee.Geometry.Rectangle(aoi['bbox']))
    acc = np.zeros((height,width),np.float32)
    weights = np.zeros_like(acc)
    weight = np.maximum(np.outer(np.hanning(SIZE),np.hanning(SIZE)),.01).astype('float32')
    coordinates = [(r,c) for r in window_starts(height) for c in window_starts(width)]
    def fetch(rc):
        r,c = rc
        return rc,download_chip(image,left+c*RES,top-r*RES,epsg)
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        # map pode baixar adiantado; limite de memória pela quantidade da AOI.
        for i,((r,c),(x,valid,_)) in enumerate(pool.map(fetch,coordinates)):
            p = predict_array(x,valid)
            h,w = min(SIZE,height-r),min(SIZE,width-c)
            weighted = weight[:h,:w]*valid[:h,:w]
            acc[r:r+h,c:c+w] += p[:h,:w]*weighted
            weights[r:r+h,c:c+w] += weighted
            if (i+1)%10==0 or i==len(coordinates)-1:
                print(aoi['autex'],i+1,'/',len(coordinates),'janelas')
    observed = weights>0
    prob = np.full((height,width),-9999,np.float32)
    prob[observed] = acc[observed]/weights[observed]
    mask = np.full((height,width),255,np.uint8)
    mask[observed] = (prob[observed]>=.5).astype(np.uint8)
    name = re.sub(r'[^A-Za-z0-9_-]','_',aoi['autex'])
    for prefix,arr,nodata in [('prob',prob,-9999),('mask',mask,255)]:
        with rasterio.open(OUT/f'{prefix}_{name}.tif','w',driver='GTiff',
                           height=height,width=width,count=1,dtype=arr.dtype,
                           crs=f'EPSG:{epsg}',transform=affine,nodata=nodata,
                           compress='deflate',tiled=True) as dst:
            dst.write(arr,1)
            dst.update_tags(modelo=MODEL_NAME,autex=aoi['autex'],aviso='Triagem experimental; não constitui prova')
    return dict(autex=aoi['autex'],epsg=epsg,width=width,height=height,
                valid_fraction=float(observed.mean()),tiles=len(coordinates))

CONFIG['aoi_results'] = [infer_aoi(a) for a in AOIS]

# %% Empacotar e baixar
import shutil, importlib.metadata
CONFIG['versions'] = {p:importlib.metadata.version(p) for p in
                      ['torch','numpy','earthengine-api','rasterio','lightgbm','segmentation-models-pytorch']}
try:
    CONFIG['versions']['terratorch'] = importlib.metadata.version('terratorch')
except importlib.metadata.PackageNotFoundError:
    pass
(OUT/'config.json').write_text(json.dumps(CONFIG,indent=2,ensure_ascii=False,default=str),encoding='utf-8')
(OUT/'LEIA-ME.txt').write_text('\n'.join(OBS)+'\n'+PROTOCOL,encoding='utf-8')
archive = shutil.make_archive(str(ROOT/'lastro_dl_resultados'),'zip',OUT)
if SALVAR_DRIVE:
    shutil.copy2(archive,'/content/drive/MyDrive/lastro_dl_resultados.zip')
print('Resultado:',archive,'; modelo:',MODEL_NAME)
from google.colab import files
files.download(archive)
