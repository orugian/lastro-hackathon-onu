// Espelho TypeScript de contracts/models.py (contrato v1). Não divergir.
export type TipoAutorizacao = "POA" | "ASV" | "UAS";
export type Severidade = "alta" | "media" | "baixa" | "info";
export type SourceMode = "real" | "simulado";
export type FlagCodigo = "A" | "B" | "C" | "D" | "E" | "F2" | "F6";
export type Status = "indicio" | "inconclusivo" | "sem_indicio" | "nao_avaliado";

export interface Faixa { p10: number | null; p50: number | null; p90: number | null }
export interface Validade { inicio: string | null; fim: string | null }

export interface FlagResumo {
  codigo: FlagCodigo; titulo: string; status: Status; severidade: Severidade; confianca: number;
}
export interface Evidencia {
  tipo: "metrica" | "geometria" | "imagem" | "documento" | "texto";
  descricao: string; valor?: number | null; unidade?: string | null;
  camada?: string | null; filtro?: Record<string, unknown> | null; fonte?: string | null;
}
export interface Flag extends FlagResumo {
  regra: string; evidencias: Evidencia[]; volume_m3?: Faixa | null; area_ha?: number | null;
}

export interface CaseSummary {
  autex: string; tipo: TipoAutorizacao; uf: string; municipio: string;
  centroide: [number, number]; bbox: [number, number, number, number];
  area_autorizada_ha: number | null; validade: Validade; situacao: string | null;
  volume_autorizado_m3: number | null; volume_declarado_explorado_m3: number | null;
  volume_estimado_m3: Faixa; area_disturbio_ha: number | null; area_disturbio_fora_ha: number | null;
  n_arvores_declaradas: number | null; flags: FlagResumo[]; score: number;
  source_mode: SourceMode; analise_imagem: boolean; processado_em: string;
}
export interface Index {
  schema_version: string; gerado_em: string; polo: string;
  totais: Record<string, number>; casos: CaseSummary[];
}
export interface Imagem {
  id: string; sensor: "Sentinel-2" | "CBERS-4A WPM" | "Derivado" | "Modelo"; rotulo: string;
  data: string | null; png: string; bounds: [number, number, number, number];
  resolucao_m: number | null; nuvem_pct: number | null; par: "pre" | "pos" | null;
}
export interface Proveniencia {
  id: string; fonte: string; url: string; consultado_em: string; versao: string | null; licenca: string | null;
}
export interface ParametroVolume { nome: string; distribuicao: string; valor: number | null; unidade: string | null; origem: string }
export interface Especie {
  nome_cientifico: string; nome_popular: string | null; volume_autorizado_m3: number | null;
  volume_explorado_m3: number | null; n_arvores: number | null;
}
export interface Dossier extends CaseSummary {
  schema_version: string; flags_detalhe: Flag[]; imagens: Imagem[]; camadas: string[];
  especies: Especie[]; parametros_volume: ParametroVolume[]; modelo: Record<string, string>;
  proveniencia: Proveniencia[]; limitacoes: string[];
  linha_do_tempo: { data: string; evento: string; fonte?: string }[];
  legal_conclusion: false; aviso: string;
}

export type CelulaClasse = "consistente" | "sem_lastro" | "nao_declarado" | "sem_atividade" | "nao_observavel";
export interface CelulaProps {
  id: string; vol_declarado: number; n_arvores: number; disturbio_frac: number | null;
  vol_p10: number | null; vol_p50: number | null; vol_p90: number | null; classe: CelulaClasse; dentro_upa: boolean;
}
export interface ArvoreProps {
  id: string; especie: string; vol_autorizado: number | null; vol_explorado: number | null;
  data_exploracao: string | null; dentro_upa: boolean;
}
export interface MudancaProps {
  id: string; area_ha: number; prob: number; dentro_upa: boolean; dist_limite_m: number;
  data_inicio: string | null; data_fim: string | null; metodo: string;
}

export interface MetricaModelo {
  nome: string; iou: number | null; f1: number | null; precisao: number | null; recall: number | null;
  matriz_confusao: number[][] | null; n_pixels_teste: number | null; obs: string | null;
}
export interface MetricsDetector { protocolo: string; rotulos: string; modelos: MetricaModelo[]; selecionado: string; gerado_em: string }
export interface MetricsCalibracao {
  protocolo: string; n_celulas_treino: number; n_upas: number; r2: number | null; mae_m3_ha: number | null;
  cobertura_p10_p90: number | null; cobertura_nominal: number;
  curva: { disturbio_frac: number; p10: number; p50: number; p90: number }[]; obs: string | null; gerado_em: string;
}
