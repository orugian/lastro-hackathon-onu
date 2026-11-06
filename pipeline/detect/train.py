"""GroupKFold espacial externo e escolha de limiar em validacao interna por bloco."""
import json,time
from pathlib import Path
from datetime import datetime,timezone
import numpy as np,pandas as pd,lightgbm as lgb
from sklearn.model_selection import GroupKFold,GroupShuffleSplit
from sklearn.metrics import f1_score,precision_score,recall_score,jaccard_score,confusion_matrix
from contracts.models import MetricsDetector
from .common import BANDS,FEATURES,features
ROOT=Path('data/processed/ml')
def folds(groups):
    return list(GroupKFold(5).split(np.zeros(len(groups)),groups=groups))
def model():
    return lgb.LGBMClassifier(n_estimators=200,num_leaves=23,max_depth=7,learning_rate=.05,min_child_samples=60,colsample_bytree=.9,reg_lambda=2,n_jobs=4,verbosity=-1,random_state=42)
def metrics(y,p):
    return dict(iou=float(jaccard_score(y,p,zero_division=0)),f1=float(f1_score(y,p,zero_division=0)),precisao=float(precision_score(y,p,zero_division=0)),recall=float(recall_score(y,p,zero_division=0)),matriz_confusao=confusion_matrix(y,p,labels=[0,1]).tolist(),n_pixels_teste=len(y))
def best_threshold(y,p):
    thresholds=np.linspace(.05,.95,91)
    return float(thresholds[np.argmax([f1_score(y,p>=t,zero_division=0) for t in thresholds])])
def main():
    started=time.perf_counter()
    if not (ROOT/'dataset.parquet').exists():
        from .dataset import main as build
        build()
    from .dataset import exclude_demo_rows
    df,exclusion_note=exclude_demo_rows(pd.read_parquet(ROOT/'dataset.parquet'))
    x=features(df[BANDS].to_numpy()); y=(df.label.to_numpy()>0).astype(int); groups=df.bloco.to_numpy()
    if len(set(groups))<5: raise ValueError('Necessarios pelo menos cinco blocos reais')
    pred=np.zeros(len(y),dtype=int); probabilities=np.zeros(len(y)); report=[]; thresholds=[]
    for fold,(tr,te) in enumerate(folds(groups)):
        itr,iva=next(GroupShuffleSplit(n_splits=1,test_size=.25,random_state=42+fold).split(x[tr],y[tr],groups[tr]))
        inner=model().fit(x[tr[itr]],y[tr[itr]],feature_name=FEATURES)
        threshold=best_threshold(y[tr[iva]],inner.booster_.predict(x[tr[iva]],num_threads=4)); thresholds.append(threshold)
        fitted=model().fit(x[tr],y[tr],feature_name=FEATURES); probabilities[te]=fitted.booster_.predict(x[te],num_threads=4); pred[te]=probabilities[te]>=threshold
        report.append(dict(fold=fold,train_blocks=sorted(set(groups[tr])),test_blocks=sorted(set(groups[te])),threshold=threshold,**metrics(y[te],pred[te])))
    limitations='Rotulos fracos: DETER (~3 ha) e PRODES (6,25 ha) nao captam todas as pequenas clareiras. Datas anuais podem incluir eventos posteriores a mediana jun-set; negativos usam NDVI pre >0,75 e exclusao de todos os alertas DETER e PRODES 2008+. Pixels balanceados nao representam prevalencia operacional. Blocos adjacentes nao tem buffer de separacao. Probabilidade nao calibrada; resultado e indicio para priorizar fiscalizacao, nunca prova.'
    manifest=json.loads((ROOT/'manifest.json').read_text()) if (ROOT/'manifest.json').exists() else {}
    manifest['demo_exclusion']=exclusion_note
    results=[]
    for name,p in [('baseline-otsu',df.baseline.to_numpy().astype(int)),('lightgbm',pred)]:
        strata={}
        for label,title in [(1,'corte_raso'),(2,'seletivo_degradacao')]:
            keep=(df.label.to_numpy()==0)|(df.label.to_numpy()==label)
            strata[title]=metrics(y[keep],p[keep]) if (df.label==label).any() else None
        results.append(dict(nome=name,**metrics(y,p),obs=limitations+' Por tipo (mesmos negativos estaveis em cada estrato): '+json.dumps(strata,ensure_ascii=False)+'; exclusao demo: '+str(manifest.get('demo_exclusion','nao verificada'))))
    final=model().fit(x,y,feature_name=FEATURES); final.booster_.save_model(str(ROOT/'lgbm_detector.txt'))
    threshold=float(np.median(thresholds)); (ROOT/'threshold.json').write_text(json.dumps({'threshold':threshold,'features':FEATURES,'stack_bands':BANDS,'delta':'pos-pre','reflectance_scale':1,'fold_thresholds':thresholds,'method':'mediana de limiares de validacao interna espacial'}))
    elapsed=time.perf_counter()-started
    selected=max(results,key=lambda r:r['f1'])['nome']
    payload=MetricsDetector(protocolo=f'GroupKFold espacial externo k=5, blocos fixos 5 km EPSG:31980; {len(set(groups))} blocos, {len(y)} pixels. Limiar LightGBM escolhido por F1 em holdout interno por bloco (25%), sem usar teste externo. Reajuste em todo treino externo. Baseline Otsu nao supervisionado por tile completo e abertura 3x3 antes de amostrar. Metricas agregadas out-of-fold. Modelo final ajustado em todos os blocos. Tempo treino e avaliacao {elapsed:.2f} s.',rotulos='INPE PRODES anual e DETER: corte raso, CS_DESORDENADO, CS_GEOMETRICO, DEGRADACAO; 2022-2024; AMACRO',modelos=results,selecionado=selected,gerado_em=datetime.now(timezone.utc).isoformat())
    target=Path('data/artifacts/metrics/detector.json'); target.parent.mkdir(parents=True,exist_ok=True); target.write_text(payload.model_dump_json(indent=2),encoding='utf-8')
    (ROOT/'validation.json').write_text(json.dumps({'folds':report,'training_seconds':elapsed,'n_blocks':len(set(groups))},indent=2))
    df[['bloco','year','label']].assign(prob_oof=probabilities,pred_oof=pred).to_parquet(ROOT/'oof.parquet',index=False)
    print(payload.model_dump_json(indent=2)); print('TRAIN_SECONDS',elapsed)
if __name__=='__main__': main()
