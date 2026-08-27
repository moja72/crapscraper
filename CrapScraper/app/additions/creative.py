def image_prompt(job):
    kind="tema exibido em monitor e celular" if job["kind"]=="theme" else "caixa 3D profissional com pelo menos três faces"
    return f"Imagem de capa quadrada 1:1, fundo transparente, alta qualidade, para {job['product_name']}, {kind}. Use somente a identidade visual verdadeira verificável do produto; não invente logotipo. Sem preço e sem texto pequeno."
