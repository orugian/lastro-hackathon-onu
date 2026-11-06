# Lastro — apresentação executiva V2

## Brief confirmado
- Banca de hackathon com diretores; 7 minutos.
- Reformatar e reestruturar V1, com visão de negócio e números reais.
- Referências fornecidas: 3C Conecta e NewAI. Herdar grandes títulos, narrativa de problema a demonstração, alternância claro/escuro, formato 16:9 e reservas técnicas. Não herdar estatísticas, marcas ou cores desses projetos.
- Preservar todos os originais e não modificar o produto.

## Direção da apresentação
Modo: Persuade / apresentação, não landing page. Extensão da identidade Lastro já existente (floresta e lima), com tipografia Figtree embutida na referência NewAI. Aplicar composição editorial, texto curto e evidência como imagem. A direção sorteada `editorial-report` (seed 1903804647) organiza títulos e dados; o brief de slides e as referências prevalecem sobre módulos de página contínua, navegação de site e animações de rolagem. Sem fotografias externas, imagens geradas ou dados ilustrativos disfarçados de reais.

Inventário próprio: 1.142 autorizações; AMACRO; 329.288 registros de árvores; IF100; 1,87 milhão de m³ declarados; 62 casos com indícios; 39 com imagem; 45 coordenadas fora do polígono no caso; 490 datas fora da validade; intervalo de volume; dossiê rastreável; revisão humana.

Ideia: **a passagem de 1.142 autorizações a 62 casos com indícios se torna a composição editorial da priorização**, com denominadores e limitações visíveis. Não é prevalência de ilegalidade nem economia medida. Elemento vivo: alternar imagem anterior/posterior e abrir as evidências documental, temporal e de volume do mesmo caso, sem rede.

## Direction contract
THESIS: evidência suficiente para decidir onde olhar; recusar o pitch de IA genérica e a exposição de arquitetura antes do problema.
OWN-WORLD: campos verde floresta, branco quase neutro e lima; Figtree; números grandes; mapas reais e colunas abertas, sem cartões repetidos, gradientes ou sombra decorativa.
STORY: dimensão do problema → fila real → caso demonstrável → mecanismo → usuário e comprador → valor econômico a medir → confiança → piloto proposto → convite.
FIRST VIEWPORT: faixa superior com imagens Sentinel-2 do caso, Lastro grande embaixo à esquerda e promessa operacional à direita; navegação discreta fora do slide. Contraste forte para projeção em sala.
FORM: editorial-report, seed 1903804647; deck 16:9 definido pelo brief e pelas referências. Transição curta, sem animação necessária para entender o slide. Mobile em leitura vertical.
FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance.

## Argumento, prova e tempo
| Slide | Tese | Prova / condição | Tempo |
|---|---|---|---|
| 1 | Lastro organiza evidências para priorizar fiscalização | Imagem real e definição explícita de triagem | 20 s |
| 2 | O gargalo é decidir onde olhar | 1.142 autorizações, 329.288 registros, 1,87 mi m³ | 35 s |
| 3 | Há uma fila real, não apenas uma ideia | 62/1.142 com indícios; 39 com imagem; recálculo sem simulação | 40 s |
| 4 | Um caso permite verificar o raciocínio | Candeias do Jamari: 45/494 coordenadas e 490/494 datas; A sem indício | 80 s |
| 5 | O diferencial é juntar a evidência por autorização | Documento + declaração + imagem → dossiê com regra, limiar e fonte | 40 s |
| 6 | A entrada é institucional | Usuário e comprador como hipóteses comerciais, sem parceria alegada | 45 s |
| 7 | O valor econômico deve ser medido | Horas liberadas e custo total; fórmula, não ROI fictício | 45 s |
| 8 | A confiança depende de limites explícitos | 39/1.142 imagem; validação interna e revisão humana | 40 s |
| 9 | Um piloto pode testar a utilidade | Proposta de 90 dias, etapas e critérios acordados antes do teste | 45 s |
| 10 | O próximo passo é validar com quem decide | Convite a parceiro técnico, sem investimento fictício | 30 s |

Total: 420 s. Reservas: auditoria de números; métricas técnicas e limites; modelo econômico; fontes.

## Integridade
- Recalcular contagens no array `casos`, filtrando `source_mode === 'real'`. O cabeçalho e roteiro antigo são inconsistentes; documentar sem alterar dados originais.
- O dossiê é mais novo que o índice. Usar exclusivamente o dossiê congelado para o caso; não misturar score/área entre versões.
- Registros de árvores não equivalem a contagem independente de árvores únicas.
- Volume declarado não equivale a madeira irregular, volume recuperado, perda financeira, receita ou mercado endereçável.
- Cenários SIM não entram no agregado.
- Hipóteses comerciais e cronograma de piloto são propostas, não realizações.
- A validação de volume usa declaração IF100, não cubagem independente de campo.
- Nenhum AUTEX completo no conteúdo projetado. Nenhum CPF, CNPJ ou nome de detentor.
