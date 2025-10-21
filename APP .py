# ============================================
# APLICACIÓN STREAMLIT - GESTIÓN DE PEDIDOS
# Sistema Completo de Medicamentos
# ============================================

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import psycopg2
from psycopg2.extras import RealDictCursor
import qrcode
from io import BytesIO
import base64
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
import hashlib
import json

# ============================================
# CONFIGURACIÓN DE LA PÁGINA
# ============================================

st.set_page_config(
    page_title="Sistema de Pedidos - Farmacia",
    page_icon="💊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================================
# ESTILOS CSS PERSONALIZADOS
# ============================================

st.markdown("""
    <style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1f77b4;
        text-align: center;
        padding: 20px;
        background: linear-gradient(90deg, #e3f2fd 0%, #bbdefb 100%);
        border-radius: 10px;
        margin-bottom: 30px;
    }
    .metric-card {
        background-color: #f0f8ff;
        padding: 20px;
        border-radius: 10px;
        border-left: 5px solid #1f77b4;
    }
    .success-box {
        background-color: #d4edda;
        padding: 15px;
        border-radius: 5px;
        border-left: 4px solid #28a745;
        color: #155724;
    }
    .warning-box {
        background-color: #fff3cd;
        padding: 15px;
        border-radius: 5px;
        border-left: 4px solid #ffc107;
        color: #856404;
    }
    .error-box {
        background-color: #f8d7da;
        padding: 15px;
        border-radius: 5px;
        border-left: 4px solid #dc3545;
        color: #721c24;
    }
    </style>
""", unsafe_allow_html=True)

# ============================================
# CONFIGURACIÓN DE BASE DE DATOS SUPABASE
# ============================================

class DatabaseConnection:
    """Clase para manejar la conexión con Supabase PostgreSQL"""
    
    def __init__(self):
        # IMPORTANTE: Reemplaza estos valores con tus credenciales de Supabase
        self.config = {
            'host': 'db.xxxxxxxxxx.supabase.co',  # Tu host de Supabase
            'database': 'postgres',
            'user': 'postgres',
            'password': 'tu_password_supabase',  # Tu contraseña
            'port': '5432'
        }
    
    def get_connection(self):
        """Establece conexión con la base de datos"""
        try:
            conn = psycopg2.connect(**self.config)
            return conn
        except Exception as e:
            st.error(f"Error de conexión a base de datos: {str(e)}")
            return None
    
    def execute_query(self, query, params=None, fetch=True):
        """Ejecuta una consulta SQL"""
        conn = self.get_connection()
        if conn is None:
            return None
        
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(query, params)
                if fetch:
                    result = cursor.fetchall()
                    conn.commit()
                    return result
                else:
                    conn.commit()
                    return cursor.rowcount
        except Exception as e:
            conn.rollback()
            st.error(f"Error en consulta: {str(e)}")
            return None
        finally:
            conn.close()
    
    def execute_insert(self, query, params=None):
        """Ejecuta un INSERT y retorna el ID generado"""
        conn = self.get_connection()
        if conn is None:
            return None
        
        try:
            with conn.cursor() as cursor:
                cursor.execute(query, params)
                inserted_id = cursor.fetchone()[0]
                conn.commit()
                return inserted_id
        except Exception as e:
            conn.rollback()
            st.error(f"Error en inserción: {str(e)}")
            return None
        finally:
            conn.close()

# Instancia global de la base de datos
db = DatabaseConnection()

# ============================================
# FUNCIONES DE CLIENTES
# ============================================

def verificar_cliente_existente(telefono):
    """Verifica si un cliente existe en la base de datos"""
    query = "SELECT * FROM clientes WHERE telefono = %s"
    result = db.execute_query(query, (telefono,))
    return result[0] if result else None

def registrar_nuevo_cliente(datos_cliente):
    """Registra un nuevo cliente en la base de datos"""
    query = """
        INSERT INTO clientes (nombre, telefono, email, direccion, referencia, distrito, provincia, departamento)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    """
    params = (
        datos_cliente['nombre'],
        datos_cliente['telefono'],
        datos_cliente.get('email'),
        datos_cliente['direccion'],
        datos_cliente.get('referencia'),
        datos_cliente.get('distrito', 'Lima'),
        datos_cliente.get('provincia', 'Lima'),
        datos_cliente.get('departamento', 'Lima')
    )
    return db.execute_insert(query, params)

# ============================================
# FUNCIONES DE MEDICAMENTOS
# ============================================

def obtener_medicamentos_disponibles():
    """Obtiene todos los medicamentos con stock disponible"""
    query = """
        SELECT * FROM medicamentos 
        WHERE activo = TRUE AND stock > 0
        ORDER BY categoria, nombre
    """
    result = db.execute_query(query)
    return pd.DataFrame(result) if result else pd.DataFrame()

def verificar_stock_medicamento(medicamento_id, cantidad):
    """Verifica si hay stock suficiente"""
    query = "SELECT stock FROM medicamentos WHERE id = %s"
    result = db.execute_query(query, (medicamento_id,))
    if result:
        return result[0]['stock'] >= cantidad
    return False

# ============================================
# FUNCIONES DE PEDIDOS
# ============================================

def generar_numero_pedido():
    """Genera un número único de pedido"""
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    return f"PED-{timestamp}"

def crear_pedido(cliente_id, items, direccion_envio, observaciones=""):
    """Crea un nuevo pedido en la base de datos"""
    # Calcular totales
    subtotal = sum(item['subtotal'] for item in items)
    impuesto = subtotal * 0.18  # IGV 18%
    total = subtotal + impuesto
    
    numero_pedido = generar_numero_pedido()
    
    # Insertar pedido
    query_pedido = """
        INSERT INTO pedidos (
            numero_pedido, cliente_id, subtotal, impuesto, total, 
            estado, direccion_envio, observaciones
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    """
    params_pedido = (
        numero_pedido, cliente_id, subtotal, impuesto, 
        total, 'PENDIENTE', direccion_envio, observaciones
    )
    
    pedido_id = db.execute_insert(query_pedido, params_pedido)
    
    if pedido_id:
        # Insertar detalles del pedido
        for item in items:
            query_detalle = """
                INSERT INTO detalle_pedidos (
                    pedido_id, medicamento_id, codigo_medicamento, 
                    nombre_medicamento, cantidad, precio_unitario, 
                    subtotal, total_item
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """
            params_detalle = (
                pedido_id, item['medicamento_id'], item['codigo'],
                item['nombre'], item['cantidad'], item['precio_unitario'],
                item['subtotal'], item['subtotal']
            )
            db.execute_query(query_detalle, params_detalle, fetch=False)
        
        return pedido_id, numero_pedido, total
    
    return None, None, None

def actualizar_estado_pedido(pedido_id, nuevo_estado):
    """Actualiza el estado de un pedido"""
    query = """
        UPDATE pedidos 
        SET estado = %s, 
            fecha_confirmacion = CASE WHEN %s = 'CONFIRMADO' THEN CURRENT_TIMESTAMP ELSE fecha_confirmacion END,
            fecha_pago = CASE WHEN %s = 'PAGADO' THEN CURRENT_TIMESTAMP ELSE fecha_pago END,
            fecha_envio = CASE WHEN %s = 'ENVIADO' THEN CURRENT_TIMESTAMP ELSE fecha_envio END
        WHERE id = %s
    """
    return db.execute_query(query, (nuevo_estado, nuevo_estado, nuevo_estado, nuevo_estado, pedido_id), fetch=False)

def registrar_pago(pedido_id, monto, metodo_pago, referencia):
    """Registra un pago en la base de datos"""
    query = """
        INSERT INTO pagos (pedido_id, monto, metodo_pago, referencia)
        VALUES (%s, %s, %s, %s)
        RETURNING id
    """
    pago_id = db.execute_insert(query, (pedido_id, monto, metodo_pago, referencia))
    
    if pago_id:
        # Actualizar estado del pedido
        actualizar_estado_pedido(pedido_id, 'PAGADO')
    
    return pago_id

# ============================================
# FUNCIONES DE GENERACIÓN DE QR
# ============================================

def generar_qr_pedido(pedido_info):
    """Genera un código QR con la información del pedido"""
    # Crear datos del QR
    qr_data = {
        'pedido': pedido_info['numero_pedido'],
        'cliente': pedido_info['cliente_nombre'],
        'total': float(pedido_info['total']),
        'fecha': pedido_info['fecha'].strftime('%Y-%m-%d %H:%M:%S')
    }
    
    # Generar QR
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(json.dumps(qr_data))
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    
    # Convertir a base64
    buffer = BytesIO()
    img.save(buffer, format='PNG')
    qr_base64 = base64.b64encode(buffer.getvalue()).decode()
    
    return qr_base64

# ============================================
# FUNCIONES DE GENERACIÓN DE PDF
# ============================================

def generar_voucher_pdf(pedido_id):
    """Genera un voucher de venta en PDF"""
    # Obtener datos del pedido
    query = """
        SELECT p.*, c.nombre as cliente_nombre, c.telefono, c.direccion
        FROM pedidos p
        JOIN clientes c ON p.cliente_id = c.id
        WHERE p.id = %s
    """
    pedido = db.execute_query(query, (pedido_id,))[0]
    
    # Obtener detalles
    query_detalles = """
        SELECT * FROM detalle_pedidos WHERE pedido_id = %s
    """
    detalles = db.execute_query(query_detalles, (pedido_id,))
    
    # Crear PDF
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    elements = []
    styles = getSampleStyleSheet()
    
    # Título
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#1f77b4'),
        spaceAfter=30,
        alignment=1
    )
    elements.append(Paragraph("VOUCHER DE VENTA", title_style))
    elements.append(Spacer(1, 0.3*inch))
    
    # Información del pedido
    info_data = [
        ['Número de Pedido:', pedido['numero_pedido']],
        ['Fecha:', pedido['fecha_pedido'].strftime('%d/%m/%Y %H:%M')],
        ['Cliente:', pedido['cliente_nombre']],
        ['Teléfono:', pedido['telefono']],
        ['Dirección:', pedido['direccion']]
    ]
    
    info_table = Table(info_data, colWidths=[2*inch, 4*inch])
    info_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.grey),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
        ('BACKGROUND', (1, 0), (1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 0.3*inch))
    
    # Tabla de productos
    elements.append(Paragraph("Detalle del Pedido", styles['Heading2']))
    elements.append(Spacer(1, 0.2*inch))
    
    productos_data = [['Código', 'Medicamento', 'Cantidad', 'P. Unit.', 'Subtotal']]
    for detalle in detalles:
        productos_data.append([
            detalle['codigo_medicamento'],
            detalle['nombre_medicamento'],
            str(detalle['cantidad']),
            f"S/ {detalle['precio_unitario']:.2f}",
            f"S/ {detalle['total_item']:.2f}"
        ])
    
    productos_table = Table(productos_data, colWidths=[1*inch, 2.5*inch, 1*inch, 1*inch, 1*inch])
    productos_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f77b4')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 11),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    elements.append(productos_table)
    elements.append(Spacer(1, 0.3*inch))
    
    # Totales
    totales_data = [
        ['Subtotal:', f"S/ {pedido['subtotal']:.2f}"],
        ['IGV (18%):', f"S/ {pedido['impuesto']:.2f}"],
        ['TOTAL:', f"S/ {pedido['total']:.2f}"]
    ]
    
    totales_table = Table(totales_data, colWidths=[4.5*inch, 2*inch])
    totales_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, -1), (-1, -1), 12),
        ('TEXTCOLOR', (0, -1), (-1, -1), colors.HexColor('#1f77b4')),
        ('LINEABOVE', (0, -1), (-1, -1), 2, colors.black),
    ]))
    elements.append(totales_table)
    
    # Generar QR
    pedido_info = {
        'numero_pedido': pedido['numero_pedido'],
        'cliente_nombre': pedido['cliente_nombre'],
        'total': pedido['total'],
        'fecha': pedido['fecha_pedido']
    }
    qr_base64 = generar_qr_pedido(pedido_info)
    
    # Agregar QR al PDF
    elements.append(Spacer(1, 0.3*inch))
    elements.append(Paragraph("Código QR del Pedido", styles['Heading3']))
    
    qr_image_data = base64.b64decode(qr_base64)
    qr_buffer = BytesIO(qr_image_data)
    qr_img = Image(qr_buffer, width=2*inch, height=2*inch)
    elements.append(qr_img)
    
    # Construir PDF
    doc.build(elements)
    buffer.seek(0)
    return buffer

def generar_reporte_ventas_pdf(fecha_inicio, fecha_fin):
    """Genera un reporte de ventas en PDF"""
    # Obtener datos
    query = """
        SELECT 
            DATE(fecha_pedido) as fecha,
            COUNT(*) as total_pedidos,
            SUM(total) as monto_total
        FROM pedidos
        WHERE estado IN ('PAGADO', 'ENVIADO', 'ENTREGADO')
        AND fecha_pedido BETWEEN %s AND %s
        GROUP BY DATE(fecha_pedido)
        ORDER BY fecha
    """
    ventas = db.execute_query(query, (fecha_inicio, fecha_fin))
    
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    elements = []
    styles = getSampleStyleSheet()
    
    # Título
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=20,
        textColor=colors.HexColor('#1f77b4'),
        spaceAfter=20,
        alignment=1
    )
    elements.append(Paragraph("REPORTE DE VENTAS", title_style))
    elements.append(Paragraph(f"Período: {fecha_inicio} al {fecha_fin}", styles['Normal']))
    elements.append(Spacer(1, 0.3*inch))
    
    # Tabla de ventas
    if ventas:
        ventas_data = [['Fecha', 'Total Pedidos', 'Monto Total']]
        total_pedidos = 0
        total_monto = 0
        
        for venta in ventas:
            ventas_data.append([
                venta['fecha'].strftime('%d/%m/%Y'),
                str(venta['total_pedidos']),
                f"S/ {venta['monto_total']:.2f}"
            ])
            total_pedidos += venta['total_pedidos']
            total_monto += float(venta['monto_total'])
        
        ventas_data.append(['TOTALES', str(total_pedidos), f"S/ {total_monto:.2f}"])
        
        ventas_table = Table(ventas_data, colWidths=[2*inch, 2*inch, 2*inch])
        ventas_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f77b4')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 11),
            ('BACKGROUND', (0, 1), (-1, -2), colors.beige),
            ('BACKGROUND', (0, -1), (-1, -1), colors.grey),
            ('TEXTCOLOR', (0, -1), (-1, -1), colors.whitesmoke),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        elements.append(ventas_table)
    else:
        elements.append(Paragraph("No hay datos para el período seleccionado", styles['Normal']))
    
    doc.build(elements)
    buffer.seek(0)
    return buffer

# ============================================
# SIMULACIÓN DE WHATSAPP (Función placeholder)
# ============================================

def enviar_whatsapp(telefono, mensaje, tipo, pedido_id=None, cliente_id=None):
    """
    Simula el envío de mensajes por WhatsApp
    En producción, integrar con API de WhatsApp Business
    """
    try:
        # Registrar en base de datos
        query = """
            INSERT INTO notificaciones_whatsapp 
            (pedido_id, cliente_id, telefono, tipo, mensaje)
            VALUES (%s, %s, %s, %s, %s)
        """
        db.execute_query(query, (pedido_id, cliente_id, telefono, tipo, mensaje), fetch=False)
        
        # Aquí iría la integración real con WhatsApp API
        # Por ejemplo: Twilio, WhatsApp Business API, etc.
        
        return True
    except Exception as e:
        st.error(f"Error al enviar WhatsApp: {str(e)}")
        return False

# ============================================
# FUNCIONES DE REPORTES Y ESTADÍSTICAS
# ============================================

def obtener_metricas_dashboard():
    """Obtiene métricas para el dashboard"""
    # Ventas del día
    query_hoy = """
        SELECT COUNT(*) as pedidos, COALESCE(SUM(total), 0) as monto
        FROM pedidos
        WHERE DATE(fecha_pedido) = CURRENT_DATE
        AND estado IN ('PAGADO', 'ENVIADO', 'ENTREGADO')
    """
    ventas_hoy = db.execute_query(query_hoy)[0]
    
    # Ventas del mes
    query_mes = """
        SELECT COUNT(*) as pedidos, COALESCE(SUM(total), 0) as monto
        FROM pedidos
        WHERE EXTRACT(MONTH FROM fecha_pedido) = EXTRACT(MONTH FROM CURRENT_DATE)
        AND EXTRACT(YEAR FROM fecha_pedido) = EXTRACT(YEAR FROM CURRENT_DATE)
        AND estado IN ('PAGADO', 'ENVIADO', 'ENTREGADO')
    """
    ventas_mes = db.execute_query(query_mes)[0]
    
    # Clientes totales
    query_clientes = "SELECT COUNT(*) as total FROM clientes"
    total_clientes = db.execute_query(query_clientes)[0]['total']
    
    # Productos con stock bajo
    query_stock = "SELECT COUNT(*) as total FROM medicamentos WHERE stock <= stock_minimo AND activo = TRUE"
    stock_bajo = db.execute_query(query_stock)[0]['total']
    
    return {
        'ventas_hoy': ventas_hoy,
        'ventas_mes': ventas_mes,
        'total_clientes': total_clientes,
        'stock_bajo': stock_bajo
    }

def obtener_ventas_diarias(dias=30):
    """Obtiene datos de ventas diarias para gráficos"""
    query = """
        SELECT 
            DATE(fecha_pedido) as fecha,
            COUNT(*) as pedidos,
            SUM(total) as monto
        FROM pedidos
        WHERE fecha_pedido >= CURRENT_DATE - INTERVAL '%s days'
        AND estado IN ('PAGADO', 'ENVIADO', 'ENTREGADO')
        GROUP BY DATE(fecha_pedido)
        ORDER BY fecha
    """
    result = db.execute_query(query, (dias,))
    return pd.DataFrame(result) if result else pd.DataFrame()

def obtener_productos_mas_vendidos(limite=10):
    """Obtiene los productos más vendidos"""
    query = """
        SELECT 
            m.nombre,
            m.categoria,
            SUM(dp.cantidad) as cantidad_vendida,
            SUM(dp.total_item) as ingresos
        FROM detalle_pedidos dp
        JOIN medicamentos m ON dp.medicamento_id = m.id
        JOIN pedidos p ON dp.pedido_id = p.id
        WHERE p.estado IN ('PAGADO', 'ENVIADO', 'ENTREGADO')
        GROUP BY m.id, m.nombre, m.categoria
        ORDER BY cantidad_vendida DESC
        LIMIT %s
    """
    result = db.execute_query(query, (limite,))
    return pd.DataFrame(result) if result else pd.DataFrame()

def obtener_ventas_por_categoria():
    """Obtiene ventas agrupadas por categoría"""
    query = """
        SELECT 
            m.categoria,
            SUM(dp.cantidad) as cantidad,
            SUM(dp.total_item) as ingresos
        FROM detalle_pedidos dp
        JOIN medicamentos m ON dp.medicamento_id = m.id
        JOIN pedidos p ON dp.pedido_id = p.id
        WHERE p.estado IN ('PAGADO', 'ENVIADO', 'ENTREGADO')
        GROUP BY m.categoria
        ORDER BY ingresos DESC
    """
    result = db.execute_query(query)
    return pd.DataFrame(result) if result else pd.DataFrame()

# ============================================
# INTERFAZ PRINCIPAL
# ============================================

def main():
    """Función principal de la aplicación"""
    
    # Header
    st.markdown('<div class="main-header">💊 Sistema de Gestión de Pedidos - Farmacia</div>', 
                unsafe_allow_html=True)
    
    # Menú lateral
    st.sidebar.title("🔹 Menú Principal")
    menu_option = st.sidebar.selectbox(
        "Seleccione una opción:",
        ["📊 Dashboard", "🛒 Nuevo Pedido", "📦 Gestión de Pedidos", 
         "👥 Clientes", "💊 Medicamentos", "📈 Reportes"]
    )
    
    # ============================================
    # DASHBOARD
    # ============================================
    if menu_option == "📊 Dashboard":
        st.header("Dashboard - Métricas en Tiempo Real")
        
        # Obtener métricas
        metricas = obtener_metricas_dashboard()
        
        # Métricas principales
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric(
                label="💰 Ventas Hoy",
                value=f"S/ {metricas['ventas_hoy']['monto']:.2f}",
                delta=f"{metricas['ventas_hoy']['pedidos']} pedidos"
            )
        
        with col2:
            st.metric(
                label="📅 Ventas del Mes",
                value=f"S/ {metricas['ventas_mes']['monto']:.2f}",
                delta=f"{metricas['ventas_mes']['pedidos']} pedidos"
            )
        
        with col3:
            st.metric(
                label="👥 Clientes Totales",
                value=metricas['total_clientes']
            )
        
        with col4:
            st.metric(
                label="⚠️ Stock Bajo",
                value=metricas['stock_bajo'],
                delta="Productos" if metricas['stock_bajo'] > 0 else None,
                delta_color="inverse"
            )
        
        st.markdown("---")
        
        # Gráficos
        col_g1, col_g2 = st.columns(2)
        
        with col_g1:
            st.subheader("📈 Ventas Últimos 30 Días")
            df_ventas = obtener_ventas_diarias(30)
            if not df_ventas.empty:
                fig_ventas = px.line(
                    df_ventas, 
                    x='fecha', 
                    y='monto',
                    title='Evolución de Ventas',
                    labels={'fecha': 'Fecha', 'monto': 'Monto (S/)'}
                )
                fig_ventas.update_traces(line_color='#1f77b4', line_width=3)
                st.plotly_chart(fig_ventas, use_container_width=True)
            else:
                st.info("No hay datos de ventas disponibles")
        
        with col_g2:
            st.subheader("🏆 Top 10 Productos Más Vendidos")
            df_top = obtener_productos_mas_vendidos(10)
            if not df_top.empty:
                fig_top = px.bar(
                    df_top.head(10),
                    x='cantidad_vendida',
                    y='nombre',
                    orientation='h',
                    title='Productos con Mayor Demanda',
                    labels={'cantidad_vendida': 'Unidades Vendidas', 'nombre': 'Producto'},
                    color='cantidad_vendida',
                    color_continuous_scale='Blues'
                )
                st.plotly_chart(fig_top, use_container_width=True)
            else:
                st.info("No hay datos de productos vendidos")
        
        # Ventas por categoría
        st.subheader("📊 Ventas por Categoría")
        df_categorias = obtener_ventas_por_categoria()
        if not df_categorias.empty:
            fig_cat = px.pie(
                df_categorias,
                values='ingresos',
                names='categoria',
                title='Distribución de Ingresos por Categoría'
            )
            st.plotly_chart(fig_cat, use_container_width=True)
        else:
            st.info("No hay datos de categorías")
    
    # ============================================
    # NUEVO PEDIDO
    # ============================================
    elif menu_option == "🛒 Nuevo Pedido":
        st.header("Crear Nuevo Pedido")
        
        # Inicializar carrito en session_state
        if 'carrito' not in st.session_state:
            st.session_state.carrito = []
        
        # Paso 1: Datos del cliente
        st.subheader("👤 Paso 1: Información del Cliente")
        
        col_c1, col_c2 = st.columns(2)
        
        with col_c1:
            telefono_cliente = st.text_input("📱 Teléfono*", placeholder="+51987654321")
            
            if telefono_cliente:
                cliente_existente = verificar_cliente_existente(telefono_cliente)
                
                if cliente_existente:
                    st.success(f"✅ Cliente encontrado: {cliente_existente['nombre']}")
                    st.session_state.cliente_id = cliente_existente['id']
                    st.session_state.cliente_nombre = cliente_existente['nombre']
                    st.session_state.cliente_direccion = cliente_existente['direccion']
                else:
                    st.info("🆕 Cliente nuevo - Complete los datos")
                    
                    nombre = st.text_input("Nombre Completo*")
                    email = st.text_input("Email")
                    direccion = st.text_area("Dirección de Envío*")
                    
                    col_d1, col_d2 = st.columns(2)
                    with col_d1:
                        distrito = st.text_input("Distrito", value="Lima")
                    with col_d2:
                        referencia = st.text_input("Referencia")
                    
                    if st.button("💾 Registrar Cliente"):
                        if nombre and direccion:
                            datos_cliente = {
                                'nombre': nombre,
                                'telefono': telefono_cliente,
                                'email': email,
                                'direccion': direccion,
                                'distrito': distrito,
                                'referencia': referencia
                            }
                            cliente_id = registrar_nuevo_cliente(datos_cliente)
                            if cliente_id:
                                st.success("✅ Cliente registrado exitosamente")
                                st.session_state.cliente_id = cliente_id
                                st.session_state.cliente_nombre = nombre
                                st.session_state.cliente_direccion = direccion
                                st.rerun()
                        else:
                            st.error("Complete los campos obligatorios")
        
        # Paso 2: Seleccionar medicamentos
        if 'cliente_id' in st.session_state:
            st.markdown("---")
            st.subheader("💊 Paso 2: Seleccionar Medicamentos")
            
            df_medicamentos = obtener_medicamentos_disponibles()
            
            if not df_medicamentos.empty:
                col_m1, col_m2, col_m3 = st.columns([3, 1, 1])
                
                with col_m1:
                    medicamento_seleccionado = st.selectbox(
                        "Seleccione medicamento:",
                        options=df_medicamentos['id'].tolist(),
                        format_func=lambda x: f"{df_medicamentos[df_medicamentos['id']==x]['nombre'].values[0]} - S/ {df_medicamentos[df_medicamentos['id']==x]['precio_unitario'].values[0]:.2f} (Stock: {df_medicamentos[df_medicamentos['id']==x]['stock'].values[0]})"
                    )
                
                with col_m2:
                    cantidad = st.number_input("Cantidad:", min_value=1, value=1)
                
                with col_m3:
                    if st.button("➕ Agregar al Carrito", use_container_width=True):
                        med_data = df_medicamentos[df_medicamentos['id'] == medicamento_seleccionado].iloc[0]
                        
                        if verificar_stock_medicamento(medicamento_seleccionado, cantidad):
                            item = {
                                'medicamento_id': medicamento_seleccionado,
                                'codigo': med_data['codigo'],
                                'nombre': med_data['nombre'],
                                'cantidad': cantidad,
                                'precio_unitario': float(med_data['precio_unitario']),
                                'subtotal': float(med_data['precio_unitario']) * cantidad
                            }
                            st.session_state.carrito.append(item)
                            st.success(f"✅ {med_data['nombre']} agregado al carrito")
                            st.rerun()
                        else:
                            st.error("❌ Stock insuficiente")
                
                # Mostrar carrito
                if st.session_state.carrito:
                    st.markdown("---")
                    st.subheader("🛒 Carrito de Compras")
                    
                    df_carrito = pd.DataFrame(st.session_state.carrito)
                    df_carrito_display = df_carrito[['codigo', 'nombre', 'cantidad', 'precio_unitario', 'subtotal']]
                    df_carrito_display.columns = ['Código', 'Medicamento', 'Cant.', 'Precio Unit.', 'Subtotal']
                    
                    st.dataframe(df_carrito_display, use_container_width=True)
                    
                    # Totales
                    subtotal_carrito = sum(item['subtotal'] for item in st.session_state.carrito)
                    igv = subtotal_carrito * 0.18
                    total_carrito = subtotal_carrito + igv
                    
                    col_t1, col_t2, col_t3 = st.columns([2, 1, 1])
                    with col_t2:
                        st.metric("Subtotal", f"S/ {subtotal_carrito:.2f}")
                        st.metric("IGV (18%)", f"S/ {igv:.2f}")
                    with col_t3:
                        st.metric("TOTAL", f"S/ {total_carrito:.2f}")
                    
                    col_b1, col_b2 = st.columns(2)
                    with col_b1:
                        if st.button("🗑️ Vaciar Carrito"):
                            st.session_state.carrito = []
                            st.rerun()
                    
                    with col_b2:
                        if st.button("✅ Generar Proforma", type="primary", use_container_width=True):
                            # Crear pedido
                            observaciones = st.text_area("Observaciones (opcional):", key="obs")
                            
                            pedido_id, numero_pedido, total = crear_pedido(
                                st.session_state.cliente_id,
                                st.session_state.carrito,
                                st.session_state.cliente_direccion,
                                observaciones
                            )
                            
                            if pedido_id:
                                st.success(f"✅ Pedido creado: {numero_pedido}")
                                
                                # Actualizar estado a PROFORMA_GENERADA
                                actualizar_estado_pedido(pedido_id, 'PROFORMA_GENERADA')
                                
                                # Enviar notificación WhatsApp (simulado)
                                mensaje = f"Hola {st.session_state.cliente_nombre}, tu proforma #{numero_pedido} ha sido generada. Total: S/ {total:.2f}"
                                enviar_whatsapp(
                                    telefono_cliente,
                                    mensaje,
                                    'PROFORMA',
                                    pedido_id,
                                    st.session_state.cliente_id
                                )
                                
                                st.session_state.carrito = []
                                st.balloons()
                                st.rerun()
            else:
                st.warning("No hay medicamentos disponibles")
    
    # ============================================
    # GESTIÓN DE PEDIDOS
    # ============================================
    elif menu_option == "📦 Gestión de Pedidos":
        st.header("Gestión de Pedidos")
        
        # Filtros
        col_f1, col_f2, col_f3 = st.columns(3)
        with col_f1:
            filtro_estado = st.selectbox(
                "Estado:",
                ["Todos", "PENDIENTE", "PROFORMA_GENERADA", "CONFIRMADO", "PAGADO", "ENVIADO", "ENTREGADO", "CANCELADO"]
            )
        
        # Obtener pedidos
        if filtro_estado == "Todos":
            query = """
                SELECT p.*, c.nombre as cliente_nombre, c.telefono
                FROM pedidos p
                JOIN clientes c ON p.cliente_id = c.id
                ORDER BY p.fecha_pedido DESC
                LIMIT 50
            """
            pedidos = db.execute_query(query)
        else:
            query = """
                SELECT p.*, c.nombre as cliente_nombre, c.telefono
                FROM pedidos p
                JOIN clientes c ON p.cliente_id = c.id
                WHERE p.estado = %s
                ORDER BY p.fecha_pedido DESC
                LIMIT 50
            """
            pedidos = db.execute_query(query, (filtro_estado,))
        
        if pedidos:
            for pedido in pedidos:
                with st.expander(f"📦 Pedido {pedido['numero_pedido']} - {pedido['estado']} - S/ {pedido['total']:.2f}"):
                    col_p1, col_p2 = st.columns([2, 1])
                    
                    with col_p1:
                        st.write(f"**Cliente:** {pedido['cliente_nombre']}")
                        st.write(f"**Teléfono:** {pedido['telefono']}")
                        st.write(f"**Fecha:** {pedido['fecha_pedido'].strftime('%d/%m/%Y %H:%M')}")
                        st.write(f"**Dirección:** {pedido['direccion_envio']}")
                    
                    with col_p2:
                        nuevo_estado = st.selectbox(
                            "Actualizar estado:",
                            ["PROFORMA_GENERADA", "CONFIRMADO", "PAGADO", "ENVIADO", "ENTREGADO", "CANCELADO"],
                            key=f"estado_{pedido['id']}"
                        )
                        
                        if st.button("💾 Actualizar", key=f"btn_{pedido['id']}"):
                            if actualizar_estado_pedido(pedido['id'], nuevo_estado):
                                st.success("✅ Estado actualizado")
                                
                                if nuevo_estado == 'PAGADO':
                                    # Generar voucher
                                    voucher_pdf = generar_voucher_pdf(pedido['id'])
                                    st.download_button(
                                        label="📄 Descargar Voucher",
                                        data=voucher_pdf,
                                        file_name=f"voucher_{pedido['numero_pedido']}.pdf",
                                        mime="application/pdf"
                                    )
                                
                                st.rerun()
        else:
            st.info("No hay pedidos disponibles")
    
    # ============================================
    # CLIENTES
    # ============================================
    elif menu_option == "👥 Clientes":
        st.header("Gestión de Clientes")
        
        query = """
            SELECT * FROM clientes 
            ORDER BY fecha_registro DESC
            LIMIT 100
        """
        clientes = db.execute_query(query)
        
        if clientes:
            df_clientes = pd.DataFrame(clientes)
            st.dataframe(df_clientes[[
                'nombre', 'telefono', 'email', 'distrito', 
                'total_compras', 'monto_total_gastado', 'ultima_compra'
            ]], use_container_width=True)
        else:
            st.info("No hay clientes registrados")
    
    # ============================================
    # MEDICAMENTOS
    # ============================================
    elif menu_option == "💊 Medicamentos":
        st.header("Catálogo de Medicamentos")
        
        tab1, tab2 = st.tabs(["📋 Catálogo", "➕ Agregar Medicamento"])
        
        with tab1:
            df_meds = obtener_medicamentos_disponibles()
            
            if not df_meds.empty:
                # Filtro por categoría
                categorias = ['Todos'] + df_meds['categoria'].unique().tolist()
                categoria_filtro = st.selectbox("Filtrar por categoría:", categorias)
                
                if categoria_filtro != 'Todos':
                    df_meds = df_meds[df_meds['categoria'] == categoria_filtro]
                
                # Mostrar medicamentos
                st.dataframe(df_meds[[
                    'codigo', 'nombre', 'categoria', 'laboratorio',
                    'precio_unitario', 'stock', 'stock_minimo'
                ]], use_container_width=True)
                
                # Medicamentos con stock bajo
                stock_bajo_df = df_meds[df_meds['stock'] <= df_meds['stock_minimo']]
                if not stock_bajo_df.empty:
                    st.warning("⚠️ Medicamentos con Stock Bajo")
                    st.dataframe(stock_bajo_df[['codigo', 'nombre', 'stock', 'stock_minimo']])
            else:
                st.info("No hay medicamentos en el catálogo")
        
        with tab2:
            st.subheader("Agregar Nuevo Medicamento")
            
            col_n1, col_n2 = st.columns(2)
            
            with col_n1:
                nuevo_codigo = st.text_input("Código*")
                nuevo_nombre = st.text_input("Nombre*")
                nuevo_laboratorio = st.text_input("Laboratorio")
                nuevo_principio = st.text_input("Principio Activo")
                nueva_concentracion = st.text_input("Concentración")
            
            with col_n2:
                nueva_presentacion = st.text_input("Presentación")
                nuevo_precio = st.number_input("Precio Unitario*", min_value=0.0, step=0.1)
                nuevo_stock = st.number_input("Stock Inicial*", min_value=0, step=1)
                nueva_categoria = st.selectbox(
                    "Categoría*",
                    ["Analgésicos", "Antibióticos", "Vitaminas", "Cardiovascular", 
                     "Gastroenterología", "Alergias", "Diabetes", "Respiratorio", "Otros"]
                )
                requiere_receta = st.checkbox("Requiere Receta")
            
            nueva_descripcion = st.text_area("Descripción")
            
            if st.button("💾 Guardar Medicamento", type="primary"):
                if nuevo_codigo and nuevo_nombre and nuevo_precio > 0:
                    query = """
                        INSERT INTO medicamentos (
                            codigo, nombre, descripcion, laboratorio, principio_activo,
                            concentracion, presentacion, precio_unitario, stock, 
                            categoria, requiere_receta
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        RETURNING id
                    """
                    params = (
                        nuevo_codigo, nuevo_nombre, nueva_descripcion, nuevo_laboratorio,
                        nuevo_principio, nueva_concentracion, nueva_presentacion,
                        nuevo_precio, nuevo_stock, nueva_categoria, requiere_receta
                    )
                    
                    med_id = db.execute_insert(query, params)
                    if med_id:
                        st.success(f"✅ Medicamento agregado exitosamente (ID: {med_id})")
                        st.balloons()
                    else:
                        st.error("❌ Error al agregar medicamento")
                else:
                    st.error("Complete los campos obligatorios")
    
    # ============================================
    # REPORTES
    # ============================================
    elif menu_option == "📈 Reportes":
        st.header("Reportes y Estadísticas")
        
        tab1, tab2, tab3 = st.tabs(["📊 Ventas", "📦 Productos", "👥 Clientes"])
        
        with tab1:
            st.subheader("Reporte de Ventas")
            
            col_r1, col_r2 = st.columns(2)
            with col_r1:
                fecha_inicio = st.date_input("Fecha Inicio", value=datetime.now() - timedelta(days=30))
            with col_r2:
                fecha_fin = st.date_input("Fecha Fin", value=datetime.now())
            
            if st.button("🔍 Generar Reporte"):
                # Obtener datos
                query = """
                    SELECT 
                        DATE(fecha_pedido) as fecha,
                        COUNT(*) as total_pedidos,
                        SUM(total) as monto_total,
                        AVG(total) as ticket_promedio
                    FROM pedidos
                    WHERE estado IN ('PAGADO', 'ENVIADO', 'ENTREGADO')
                    AND fecha_pedido BETWEEN %s AND %s
                    GROUP BY DATE(fecha_pedido)
                    ORDER BY fecha
                """
                ventas = db.execute_query(query, (fecha_inicio, fecha_fin))
                
                if ventas:
                    df_ventas_reporte = pd.DataFrame(ventas)
                    
                    # Métricas resumen
                    total_pedidos = df_ventas_reporte['total_pedidos'].sum()
                    total_ventas = df_ventas_reporte['monto_total'].sum()
                    ticket_promedio = df_ventas_reporte['ticket_promedio'].mean()
                    
                    col_m1, col_m2, col_m3 = st.columns(3)
                    with col_m1:
                        st.metric("Total Pedidos", f"{total_pedidos}")
                    with col_m2:
                        st.metric("Total Ventas", f"S/ {total_ventas:.2f}")
                    with col_m3:
                        st.metric("Ticket Promedio", f"S/ {ticket_promedio:.2f}")
                    
                    # Gráfico de ventas
                    fig = px.bar(
                        df_ventas_reporte,
                        x='fecha',
                        y='monto_total',
                        title='Ventas por Día',
                        labels={'fecha': 'Fecha', 'monto_total': 'Monto Total (S/)'}
                    )
                    st.plotly_chart(fig, use_container_width=True)
                    
                    # Tabla de datos
                    st.dataframe(df_ventas_reporte, use_container_width=True)
                    
                    # Botón de descarga PDF
                    pdf_ventas = generar_reporte_ventas_pdf(fecha_inicio, fecha_fin)
                    st.download_button(
                        label="📄 Descargar Reporte PDF",
                        data=pdf_ventas,
                        file_name=f"reporte_ventas_{fecha_inicio}_{fecha_fin}.pdf",
                        mime="application/pdf"
                    )
                else:
                    st.info("No hay datos para el período seleccionado")
        
        with tab2:
            st.subheader("Reporte de Productos")
            
            col_p1, col_p2 = st.columns(2)
            
            with col_p1:
                st.write("**Top 15 Productos Más Vendidos**")
                df_top_productos = obtener_productos_mas_vendidos(15)
                if not df_top_productos.empty:
                    fig_productos = px.bar(
                        df_top_productos,
                        x='cantidad_vendida',
                        y='nombre',
                        orientation='h',
                        color='ingresos',
                        labels={'cantidad_vendida': 'Unidades', 'nombre': 'Producto'}
                    )
                    st.plotly_chart(fig_productos, use_container_width=True)
                    st.dataframe(df_top_productos, use_container_width=True)
                else:
                    st.info("No hay datos disponibles")
            
            with col_p2:
                st.write("**Ventas por Categoría**")
                df_cat = obtener_ventas_por_categoria()
                if not df_cat.empty:
                    fig_cat = px.pie(
                        df_cat,
                        values='ingresos',
                        names='categoria',
                        title='Distribución de Ingresos'
                    )
                    st.plotly_chart(fig_cat, use_container_width=True)
                    st.dataframe(df_cat, use_container_width=True)
                else:
                    st.info("No hay datos disponibles")
            
            # Historial de movimientos de stock
            st.markdown("---")
            st.write("**Historial de Movimientos de Stock (Últimos 50)**")
            query_historial = """
                SELECT 
                    h.fecha,
                    m.nombre as medicamento,
                    h.tipo_movimiento,
                    h.cantidad,
                    h.stock_anterior,
                    h.stock_nuevo,
                    h.observaciones
                FROM historial_stock h
                JOIN medicamentos m ON h.medicamento_id = m.id
                ORDER BY h.fecha DESC
                LIMIT 50
            """
            historial = db.execute_query(query_historial)
            if historial:
                df_historial = pd.DataFrame(historial)
                st.dataframe(df_historial, use_container_width=True)
            else:
                st.info("No hay movimientos registrados")
        
        with tab3:
            st.subheader("Reporte de Clientes")
            
            # Clientes más frecuentes
            query_top_clientes = """
                SELECT 
                    nombre,
                    telefono,
                    total_compras,
                    monto_total_gastado,
                    ultima_compra,
                    CASE 
                        WHEN total_compras >= 10 THEN 'VIP'
                        WHEN total_compras >= 5 THEN 'Frecuente'
                        ELSE 'Regular'
                    END as categoria
                FROM clientes
                WHERE total_compras > 0
                ORDER BY monto_total_gastado DESC
                LIMIT 20
            """
            top_clientes = db.execute_query(query_top_clientes)
            
            if top_clientes:
                df_top_clientes = pd.DataFrame(top_clientes)
                
                col_c1, col_c2 = st.columns(2)
                
                with col_c1:
                    st.write("**Top 20 Clientes por Monto**")
                    st.dataframe(df_top_clientes, use_container_width=True)
                
                with col_c2:
                    st.write("**Distribución de Clientes por Categoría**")
                    categoria_count = df_top_clientes['categoria'].value_counts()
                    fig_clientes = px.pie(
                        values=categoria_count.values,
                        names=categoria_count.index,
                        title='Categorías de Clientes'
                    )
                    st.plotly_chart(fig_clientes, use_container_width=True)
                
                # Estadísticas generales
                st.markdown("---")
                st.write("**Estadísticas Generales de Clientes**")
                
                total_clientes_activos = len(df_top_clientes)
                promedio_compras = df_top_clientes['total_compras'].mean()
                promedio_gastado = df_top_clientes['monto_total_gastado'].mean()
                
                col_e1, col_e2, col_e3 = st.columns(3)
                with col_e1:
                    st.metric("Clientes Activos", total_clientes_activos)
                with col_e2:
                    st.metric("Promedio Compras", f"{promedio_compras:.1f}")
                with col_e3:
                    st.metric("Promedio Gastado", f"S/ {promedio_gastado:.2f}")
            else:
                st.info("No hay datos de clientes disponibles")

# ============================================
# EJECUTAR APLICACIÓN
# ============================================

if __name__ == "__main__":
    main()
    
    #