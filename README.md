# App Sísmica - GIECAR UFF

```text
   ____ _                       ____       _               _           
  / ___(_) ___  ___ __ _ _ __  / ___|  ___(_)___ _ __ ___ (_) ___ __ _ 
 | |  _| |/ _ \/ __/ _` | '__| \___ \ / _ \ / __| '_ ` _ \| |/ __/ _` |
 | |_| | |  __/ (_| (_| | |     ___) |  __/ \__ \ | | | | | | (_| (_| |
  \____|_|\___|\___\__,_|_|    |____/ \___|_|___/_| |_| |_|_|\___\__,_|
```

Processamento de Dados Sísmicos (Processo Seletivo P&D - GIECAR/UFF)
Aplicativo desenvolvido para filtragem de arquivos SEG-Y utilizando Filtros Passa-Baixa de Butterworth.

- **Interface:** GUI interativa construída com PySide6.
- **Performance:** Implementação de processamento paralelo e acesso via chunks para otimização extrema do uso de memória.

## 🚀 Requisitos e Configuração do Ambiente

O projeto foi desenvolvido em **Python 3.12+**. Recomenda-se a utilização de um ambiente virtual para isolar as dependências da aplicação.

### 1. Criar o Ambiente Virtual

Abra o terminal na pasta raiz do projeto e crie o ambiente virtual:

```bash
python -m venv .venv
```

### 2. Ativar o Ambiente Virtual

No **Linux / macOS**:
```bash
source .venv/bin/activate
```

No **Windows** (Prompt de Comando):
```cmd
.venv\Scripts\activate.bat
```

No **Windows** (PowerShell):
```powershell
.venv\Scripts\Activate.ps1
```

### 3. Instalar as Dependências

Com o ambiente ativado, instale as dependências listadas no `requirements.txt`:

```bash
pip install -r requirements.txt
```

*(Dependências principais incluem: `PySide6`, `numpy`, `scipy`, `h5py`, `segyio`, `psutil` e `SQLAlchemy`)*

---

## 🏃 Como Iniciar a Aplicação

Com o ambiente ativado e as dependências instaladas, você pode rodar a aplicação através do módulo principal:

```bash
python -m src.app_seismica
```

Ou, caso tenha o diretório `src` adicionado ao seu `PYTHONPATH`:

```bash
python -m app_seismica
```

## 🧪 Rodando os Testes

Para garantir que toda a infraestrutura lógica do filtro e a persistência de banco de dados estão funcionando corretamente, você pode rodar a suite de testes integrada ao `pytest`:

```bash
pytest tests/
```

## 📊 Benchmark e Consumo de Memória

A aplicação foi projetada de forma inteligente para não carregar arquivos gigantescos inteiros na memória RAM. Em vez disso, ela permite especificar o tamanho do **chunk** (quantidade de traços processados por vez) diretamente pela interface. 

O consumo de memória cresce proporcionalmente conforme você aumenta o tamanho do chunk para tentar acelerar o processamento em máquinas mais parrudas. 

Abaixo segue um benchmark de consumo de memória filtrando o arquivo real `volve_psdm_full_time.segy` (um volume sísmico pesado):

| Tamanho do Lote (Chunk Size) | Pico de Memória RAM (MB) |
| :---: | :---: |
| **500** | 360.0 MB |
| **5.000** | 585.0 MB |
| **50.000** | 1.857.2 MB |
| **288.694** *(Arquivo Inteiro)* | 6.918.9 MB |

> **Nota:** Configurar chunks menores (ex: 500) é recomendado para notebooks pessoais, permitindo processar dezenas de Gigabytes de dados consumindo quase nada de RAM!

## � Estrutura de Diretórios Resumida

- `src/app_seismica/` - Código-fonte principal.
  - `core/` - Modelos, comunicação com o banco de dados (SQLite) e rotinas de leitura de SEG-Y.
  - `services/` - Regras de negócio e gerenciamento dos Jobs de processamento.
  - `ui/` - Interface gráfica do usuário usando componentes do Qt (PySide6).
- `tests/` - Testes unitários e end-to-end do processamento.
- `data/` - Pasta gerada automaticamente para armazenar arquivos em processamento, logs e o banco de dados local.
