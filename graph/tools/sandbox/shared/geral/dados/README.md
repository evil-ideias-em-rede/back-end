# Guia dos dados pedagógicos

Use consultar_acervo com os caminhos abaixo. Não carregue CSVs inteiros no
prompt. A ferramenta interpreta CSV corretamente (campos com vírgulas, aspas e
quebras de linha), filtra e pagina até 20 registros por chamada. inicio é a
posição no resultado filtrado; proximo_inicio=null significa fim. Filtros de
colunas diferentes são combinados com AND e igualdade sem distinguir caixa.
Markdowns de teorias são a apresentação legível dos dados, não outra teoria.

## bncc.csv — habilidades curriculares

Colunas: id (identificador interno), code (código da habilidade), education_stage,
grade, component, field, knowledge_object, description e source_document.

- education_stage: EF_AF = Ensino Fundamental, anos finais; EM = Ensino Médio.
  Este recorte não cobre automaticamente Educação Infantil ou anos iniciais.
- grade pode reunir anos com `;`, por exemplo `6;7;8;9` ou `1;2;3`.
  O filtro grade="6" inclui os grupos que contêm 6; não faça substring arbitrária.
- component é o componente/área conforme cadastrado. Use o nome efetivamente
  retornado; consultar_bncc aceita busca de componente e informa alternativas.
- Copie code e description sem inventar redação oficial. field e knowledge_object
  ajudam a decidir pertinência; source_document registra a origem/páginas.
- Escolha poucas habilidades ligadas às ações e evidências da atividade, não
  apenas palavras do tema. Sem correspondência, explique o limite do recorte.

Exemplo de consulta (sintaxe de argumentos da ferramenta):

```json
{"arquivo":"dados/bncc.csv","filtros":{"education_stage":"EF_AF","grade":"6","component":"Ciências"}}
```

Alternativa direta: consultar_bncc(etapa="fundamental", ano="6", componente="Ciências").
Não invente uma habilidade antes de consultar. Reutilize a descrição já recuperada
se o objetivo e a turma não mudaram; trocar uma cor não exige nova busca BNCC.

## teorias-principios.csv — fundamentos e implicações

Colunas: id, theories, name, description, instructional_implication.

- id identifica o princípio, não a teoria.
- theories é uma lista JSON de nomes, não texto separado por vírgulas. O filtro
  theories compara um nome com os elementos da lista.
- name e description descrevem o princípio; instructional_implication ajuda
  a convertê-lo em uma decisão de aula. Não basta citar o autor no rodapé.

Exemplo:

```json
{"arquivo":"dados/teorias-principios.csv","filtros":{"theories":"Aprendizagem significativa — David Ausubel"}}
```

Para as demais teorias, obtenha o nome exato no índice/arquivo da teoria ou numa
primeira página do CSV, sem adivinhar grafia. Leia uma teoria escolhida em vez
de importar todos os princípios de todos os autores.

## teorias-regras.csv — ações instrucionais

Colunas: id, theory_id, principle_id, name, instruction, priority, active.

- principle_id referencia id em teorias-principios.csv; use essa relação para
  conectar ação e fundamento. Não relacione as tabelas pela posição das linhas.
- theory_id é um UUID, não o nome do arquivo Markdown. Obtenha o valor nos
  registros retornados; não invente uma correspondência de UUID com autor.
  Um princípio pode estar associado a mais de uma teoria. Para um conjunto
  exclusivo, confira também theory_id; filtrar só principle_id pode trazer
  regras compartilhadas ou ligadas a outra teoria.
- active="true" indica regra habilitada. Ignore regras desativadas.
- priority é número: 100, 80 ou 60 neste acervo. Considere as maiores primeiro,
  conforme pertinência, tempo e objetivo. Prioridade é organização interna do
  acervo, não grau de comprovação científica nem obrigação normativa da BNCC.
- instruction é a ação proposta; adapte-a à idade, ao contexto e à fonte sem
  transformar toda regra em checklist obrigatório em toda aula.

Exemplo: copie um id de princípio realmente retornado e consulte:

```json
{"arquivo":"dados/teorias-regras.csv","filtros":{"principle_id":"ID_REAL_RETORNADO","active":"true"}}
```

O ID acima é um marcador explicativo, não valor para executar. Depois de obter
um theory_id real, é possível consultar todas as regras ativas daquela teoria
e paginar. Não leia as tabelas inteiras se o Markdown selecionado já basta.

## Se consultar com código no editor

Use csv.DictReader com encoding="utf-8-sig"; json.loads para theories; int para
priority e comparação explícita com "true" para active (bool("false") é True
em Python). Separe grade por `;`. Nunca use eval, split(",") para interpretar
linhas CSV ou contagem de linhas físicas como quantidade de registros.
