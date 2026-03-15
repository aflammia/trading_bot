from datetime import datetime
from pathlib import Path

from fpdf import FPDF


OUT_PATH = Path(__file__).resolve().parent / "Manual_Usuario_Chuky_Bot.pdf"


class ManualPDF(FPDF):
    def header(self):
        if self.page_no() == 1:
            return
        self.set_fill_color(32, 18, 56)
        self.rect(0, 0, 210, 16, "F")
        self.set_text_color(255, 255, 255)
        self.set_font("Helvetica", "B", 11)
        self.set_xy(10, 5)
        self.cell(0, 6, "Chuky Bot - Manual de Usuario", 0, 0, "L")

    def footer(self):
        self.set_y(-12)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(120, 120, 120)
        self.cell(0, 6, f"Pagina {self.page_no()}", 0, 0, "C")


def section_title(pdf: ManualPDF, title: str):
    pdf.ln(4)
    pdf.set_fill_color(116, 76, 188)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, f"  {title}", 0, 1, "L", True)
    pdf.ln(2)
    pdf.set_text_color(30, 30, 30)


def bullet(pdf: ManualPDF, text: str):
    pdf.set_font("Helvetica", "", 10)
    pdf.set_x(pdf.l_margin)
    y = pdf.get_y()
    pdf.cell(4, 5, "-")
    pdf.set_xy(pdf.l_margin + 5, y)
    usable_w = pdf.w - pdf.l_margin - pdf.r_margin - 5
    pdf.multi_cell(usable_w, 5, text)


def add_cover(pdf: ManualPDF):
    pdf.add_page()
    pdf.set_fill_color(22, 12, 40)
    pdf.rect(0, 0, 210, 297, "F")

    pdf.set_fill_color(116, 76, 188)
    pdf.rect(0, 92, 210, 5, "F")

    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 32)
    pdf.ln(48)
    pdf.cell(0, 14, "CHUKY BOT", 0, 1, "C")

    pdf.set_font("Helvetica", "", 14)
    pdf.set_text_color(210, 210, 210)
    pdf.cell(0, 10, "Manual de Usuario para Traders", 0, 1, "C")

    pdf.ln(26)
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 8, "Plataforma: Streamlit + Backtesting ICT en MNQ", 0, 1, "C")
    pdf.cell(0, 8, f"Version documento: {datetime.now():%Y-%m-%d}", 0, 1, "C")

    pdf.ln(26)
    pdf.set_text_color(160, 160, 160)
    pdf.set_font("Helvetica", "I", 10)
    pdf.multi_cell(
        0,
        6,
        "Objetivo: que puedas configurar, validar y mejorar tu bot de forma clara,\n"
        "sin perder tiempo en tecnicismos innecesarios.",
        0,
        "C",
    )


def add_intro(pdf: ManualPDF):
    pdf.add_page()
    section_title(pdf, "1) Que es Chuky Bot y para que te sirve")
    bullet(pdf, "Chuky Bot es un laboratorio de trading para estrategia ICT sobre MNQ: detecta FVGs, liquidez y estructura, y ejecuta backtests con metricas profesionales.")
    bullet(pdf, "Su enfoque es ayudarte a tomar decisiones con datos: riesgo diario, drawdown, win rate, expectancy, profit factor y validacion de consistencia para prop firm.")
    bullet(pdf, "No es un bot magico: es una herramienta para mejorar proceso, disciplina y calidad de setups.")



def add_navigation(pdf: ManualPDF):
    section_title(pdf, "2) Navegacion rapida por modulos")
    modules = [
        ("Overview", "Panel general con estado de estrategia, resumen de datos y accesos rapidos."),
        ("Backtest Lab", "Ejecuta backtests por rango de fechas, ve chart interactivo, FVGs multi-TF y resultados."),
        ("Price Chart", "Visualizacion enfocada en precio y contexto tecnico."),
        ("Trades", "Explorador de operaciones, entradas/salidas y motivos de cierre."),
        ("Risk", "Control de riesgo y limites operativos de la cuenta."),
        ("Validation", "Walk-forward, Monte Carlo y metricas de robustez."),
        ("Bot Builder", "Configura parametros del sistema (FVG, estructura, riesgo, salidas)."),
        ("AI Analyst", "Asistente AI para interpretar rendimiento y proponer mejoras."),
        ("Reports", "Genera reportes y exportables para seguimiento profesional."),
    ]
    pdf.set_font("Helvetica", "", 10)
    for name, desc in modules:
        y = pdf.get_y()
        pdf.set_x(pdf.l_margin)
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(38, 6, name)
        pdf.set_xy(pdf.l_margin + 38, y)
        pdf.set_font("Helvetica", "", 10)
        desc_w = pdf.w - pdf.l_margin - pdf.r_margin - 38
        pdf.multi_cell(desc_w, 6, desc)



def add_builder(pdf: ManualPDF):
    section_title(pdf, "3) Bot Builder: parametros clave")
    bullet(pdf, "FVG Lookback por TF (1H/15M/5M/1M): define cuantas velas se escanean por timeframe.")
    bullet(pdf, "Max FVGs por TF: limita cuantas zonas activas mantiene cada timeframe.")
    bullet(pdf, "Structure Lookback 4H: sensibilidad del sesgo macro.")
    bullet(pdf, "Break-even %: en 60% del TP + ruptura de FVG de soporte se dispara cierre de proteccion.")
    bullet(pdf, "Close at TP %: cierre anticipado al porcentaje del objetivo para asegurar beneficio.")
    bullet(pdf, "Riesgo diario y max trades/dia: evita sobreoperar y protege el capital de evaluacion.")



def add_backtest_usage(pdf: ManualPDF):
    section_title(pdf, "4) Backtest Lab: flujo recomendado")
    steps = [
        "1. Selecciona rango de fechas (max 30 dias) y timeframe base.",
        "2. Ajusta o carga tu configuracion de Bot Builder.",
        "3. Ejecuta backtest y revisa primero: P&L, Max DD, Win Rate, Profit Factor.",
        "4. En chart, compara FVGs por timeframe y activa drawing tools para marcar ideas.",
        "5. Usa 'Analizar con AI' para enviar el resultado al AI Analyst.",
    ]
    for s in steps:
        bullet(pdf, s)



def add_risk(pdf: ManualPDF):
    section_title(pdf, "5) Gestion de riesgo (modo trader real)")
    bullet(pdf, "Define max_daily_loss realista para tu fase de evaluacion. Si lo rompes, se termina el dia.")
    bullet(pdf, "Prioriza consistencia: menos trades, mejor seleccionados, con objetivo de liquidez claro.")
    bullet(pdf, "Controla drawdown como variable principal; retorno sin control de DD no escala en prop firm.")
    bullet(pdf, "Revisa distribucion de perdidas: si tienes pocos losses pero muy grandes, corrige ejecucion.")



def add_ai(pdf: ManualPDF):
    section_title(pdf, "6) AI Analyst: como sacarle provecho")
    bullet(pdf, "Usa preguntas concretas: 'que sesion me esta haciendo perder?', 'que parametro empeora mi DD?'.")
    bullet(pdf, "Pidele planes accionables: 3 a 5 cambios medibles para el siguiente ciclo de pruebas.")
    bullet(pdf, "Toma AI como apoyo de analisis, no como sustituto de criterio de riesgo.")



def add_glossary(pdf: ManualPDF):
    section_title(pdf, "7) Glosario rapido")
    glossary = [
        ("FVG", "Fair Value Gap: hueco de ineficiencia de precio usado como zona de interes."),
        ("PDH/PDL", "Previous Day High / Low: liquidez del dia anterior."),
        ("Killzone", "Ventana horaria ICT con distinta calidad de movimiento."),
        ("Break-even", "Salida en precio de entrada para proteger capital."),
        ("Confluence", "Coincidencia de factores que aumenta calidad del setup."),
        ("Drawdown", "Caida desde el pico de equity; variable critica en prop trading."),
    ]
    for term, desc in glossary:
        y = pdf.get_y()
        pdf.set_x(pdf.l_margin)
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(28, 6, term)
        pdf.set_xy(pdf.l_margin + 28, y)
        pdf.set_font("Helvetica", "", 10)
        desc_w = pdf.w - pdf.l_margin - pdf.r_margin - 28
        pdf.multi_cell(desc_w, 6, desc)



def add_checklist(pdf: ManualPDF):
    section_title(pdf, "8) Checklist de inicio rapido")
    checklist = [
        "[ ] Ajuste parametros en Bot Builder (riesgo + FVG + salidas).",
        "[ ] Corra backtest de 2 a 4 semanas y valide DD, PF, expectancy.",
        "[ ] Revise chart y razones de salida de trades perdedores.",
        "[ ] Pida analisis al AI Analyst y extraiga 3 acciones concretas.",
        "[ ] Repita ciclo con un cambio a la vez para medir impacto real.",
    ]
    for item in checklist:
        bullet(pdf, item)

    pdf.ln(6)
    pdf.set_font("Helvetica", "I", 9)
    pdf.set_text_color(100, 100, 100)
    pdf.multi_cell(
        0,
        5,
        "Nota: este manual describe uso de la app y buenas practicas de evaluacion. "
        "No constituye recomendacion financiera.",
    )


def main():
    pdf = ManualPDF("P", "mm", "A4")
    pdf.set_auto_page_break(auto=True, margin=14)

    add_cover(pdf)
    add_intro(pdf)
    add_navigation(pdf)
    add_builder(pdf)
    add_backtest_usage(pdf)
    add_risk(pdf)
    add_ai(pdf)
    add_glossary(pdf)
    add_checklist(pdf)

    pdf.output(str(OUT_PATH))
    print(f"PDF generado: {OUT_PATH}")


if __name__ == "__main__":
    main()
