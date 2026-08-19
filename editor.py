# -*- coding: utf-8 -*-
"""브라우저 캔버스 편집기 (fabric.js) — 생성된 배너의 레이어를 드래그/크기/회전/텍스트 편집 후 PNG 다운로드"""
import base64
import io
import json
import os

from PIL import Image

_FONT_CACHE = {}


def _b64_png(im, max_side=None):
    if max_side and max(im.size) > max_side:
        sc = max_side / max(im.size)
        im = im.resize((int(im.width * sc), int(im.height * sc)), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _font_face_css(font_dir):
    css = []
    for fname, family in [("Jua-Regular.ttf", "Jua"), ("Gaegu-Bold.ttf", "Gaegu"),
                          ("Pretendard-ExtraBold.otf", "Pretendard")]:
        p = os.path.join(font_dir, fname)
        if not os.path.exists(p):
            continue
        if p not in _FONT_CACHE:
            _FONT_CACHE[p] = base64.b64encode(open(p, "rb").read()).decode()
        fmt = "opentype" if fname.endswith(".otf") else "truetype"
        css.append(f"@font-face{{font-family:'{family}';src:url(data:font/{fmt};base64,{_FONT_CACHE[p]}) format('{fmt}');}}")
    return "\n".join(css)


def build_editor_html(layers, pack_stickers, font_dir, file_stem):
    """layers: {"bg": PIL, "stickers": [(PIL,x,y)], "texts":[...], "size":(w,h)}"""
    w, h = layers["size"]
    bg_b64 = _b64_png(layers["bg"])
    stickers = [{"src": _b64_png(im), "x": x, "y": y} for im, x, y in layers.get("stickers", [])]
    texts = []
    for t in layers.get("texts", []):
        fam = "Jua" if "Jua" in t.get("font", "") else ("Gaegu" if "Gaegu" in t.get("font", "") else "Pretendard")
        texts.append({"text": t["text"], "x": t["x"], "y": t["y"], "size": t["size"],
                      "stroke": t["stroke"], "font": fam, "anchor": t.get("anchor", "top")})
    pack = [_b64_png(im, max_side=480) for im in pack_stickers]
    data = json.dumps({"w": w, "h": h, "bg": bg_b64, "stickers": stickers, "texts": texts,
                       "pack": pack, "name": file_stem}, ensure_ascii=False)
    css = _font_face_css(font_dir)
    return f"""<!doctype html><html><head><meta charset="utf-8">
<script src="https://cdn.jsdelivr.net/npm/fabric@5.3.0/dist/fabric.min.js"></script>
<style>
{css}
body{{margin:0;font-family:-apple-system,'Pretendard',sans-serif;background:#f6f6f8;color:#222}}
.bar{{display:flex;flex-wrap:wrap;gap:6px;align-items:center;padding:8px 10px;background:#fff;border-bottom:1px solid #e5e5ea}}
.bar button,.bar select,.bar input[type=text]{{font-size:13px;padding:6px 10px;border:1px solid #d0d0d6;border-radius:8px;background:#fff;cursor:pointer}}
.bar button.primary{{background:#FF7A59;color:#fff;border-color:#FF7A59;font-weight:700}}
.bar .sep{{width:1px;height:22px;background:#e0e0e6;margin:0 4px}}
#wrap{{padding:10px;overflow:auto}}
#c{{box-shadow:0 2px 12px rgba(0,0,0,.12);background:#fff}}
.pack{{display:flex;gap:6px;overflow-x:auto;padding:6px 10px;background:#fff;border-top:1px solid #e5e5ea}}
.pack img{{height:56px;border:1px solid #e5e5ea;border-radius:8px;cursor:pointer;background:#fafafa}}
.pack img:hover{{border-color:#FF7A59}}
.hint{{font-size:12px;color:#777;padding:4px 10px 8px}}
label{{font-size:12px;color:#555}}
</style></head><body>
<div class="bar">
  <button onclick="addText()">＋ 텍스트</button>
  <select id="font"><option value="Jua">주아(둥근)</option><option value="Gaegu">개구(손글씨)</option><option value="Pretendard">프리텐다드(고딕)</option></select>
  <label>글자색 <input type="color" id="fill" value="#1e1e22"></label>
  <label>테두리색 <input type="color" id="strokeColor" value="#ffffff"></label>
  <label>테두리 <input type="range" id="strokeW" min="0" max="30" value="8" style="width:70px"></label>
  <span class="sep"></span>
  <label>배경색 <input type="color" id="bgcol" value="#ffffff" oninput="setBg(this.value)"></label>
  <span class="sep"></span>
  <button onclick="bringFront()">맨 앞으로</button>
  <button onclick="sendBack()">맨 뒤로</button>
  <button onclick="dup()">복제</button>
  <button onclick="del()">삭제 (Del)</button>
  <button onclick="flipX()">좌우반전</button>
  <span class="sep"></span>
  <button onclick="resetAll()">처음으로</button>
  <button class="primary" onclick="download()">⬇ PNG 다운로드</button>
</div>
<div class="hint">스티커/글자를 드래그해서 옮기고, 모서리를 끌어 크기·회전을 바꾸세요. 글자는 더블클릭하면 내용을 고칠 수 있어요. 아래 목록에서 스티커를 눌러 추가할 수 있습니다.</div>
<div id="wrap"><canvas id="c"></canvas></div>
<div class="pack" id="pack"></div>
<script>
const D = {data};
const maxW = Math.min(window.innerWidth - 24, 1000);
const zoom = Math.min(1, maxW / D.w);
const canvas = new fabric.Canvas('c', {{preserveObjectStacking:true, selection:true}});
canvas.setWidth(D.w*zoom); canvas.setHeight(D.h*zoom); canvas.setZoom(zoom);
let bgImg=null;
function load(){{
  canvas.clear();
  fabric.Image.fromURL(D.bg, img=>{{
    bgImg=img; img.set({{selectable:false, evented:false, left:0, top:0}});
    canvas.setBackgroundImage(img, canvas.renderAll.bind(canvas));
  }});
  D.stickers.forEach(s=>fabric.Image.fromURL(s.src, img=>{{
    img.set({{left:s.x, top:s.y, cornerStyle:'circle', transparentCorners:false, cornerColor:'#FF7A59', borderColor:'#FF7A59'}});
    canvas.add(img); canvas.renderAll();
  }}));
  D.texts.forEach(t=>{{
    const o=new fabric.IText(t.text,{{fontFamily:t.font,fontSize:t.size,fill:'#1e1e22',stroke:'#ffffff',strokeWidth:t.stroke,paintFirst:'stroke',strokeLineJoin:'round',
      originX:'center', originY: t.anchor==='middle'?'center':'top', left:t.x, top:t.y, cornerStyle:'circle',transparentCorners:false,cornerColor:'#FF7A59',borderColor:'#FF7A59'}});
    canvas.add(o);
  }});
  canvas.renderAll();
}}
document.fonts.ready.then(load); setTimeout(()=>canvas.renderAll(),800);
function active(){{return canvas.getActiveObject();}}
function addText(){{
  const txt=prompt('넣을 문구를 입력하세요','NEW 출시!'); if(!txt)return;
  const o=new fabric.IText(txt,{{fontFamily:document.getElementById('font').value,fontSize:Math.round(D.h*0.1),fill:document.getElementById('fill').value,
    stroke:document.getElementById('strokeColor').value,strokeWidth:+document.getElementById('strokeW').value,paintFirst:'stroke',strokeLineJoin:'round',
    left:D.w/2,top:D.h/2,originX:'center',originY:'center',cornerStyle:'circle',transparentCorners:false,cornerColor:'#FF7A59',borderColor:'#FF7A59'}});
  canvas.add(o); canvas.setActiveObject(o); canvas.renderAll();
}}
['font','fill','strokeColor','strokeW'].forEach(id=>document.getElementById(id).addEventListener('input',()=>{{
  const o=active(); if(!o||o.type!=='i-text')return;
  o.set({{fontFamily:document.getElementById('font').value,fill:document.getElementById('fill').value,stroke:document.getElementById('strokeColor').value,strokeWidth:+document.getElementById('strokeW').value}});
  canvas.renderAll();
}}));
canvas.on('selection:created',syncUI); canvas.on('selection:updated',syncUI);
function syncUI(){{const o=active(); if(!o||o.type!=='i-text')return;
  document.getElementById('font').value=o.fontFamily; document.getElementById('fill').value=o.fill; document.getElementById('strokeColor').value=o.stroke||'#ffffff'; document.getElementById('strokeW').value=o.strokeWidth||0;}}
function setBg(col){{canvas.setBackgroundColor(col); canvas.setBackgroundImage(null); canvas.renderAll();}}
function bringFront(){{const o=active(); if(o){{canvas.bringToFront(o);canvas.renderAll();}}}}
function sendBack(){{const o=active(); if(o){{canvas.sendToBack(o);canvas.renderAll();}}}}
function del(){{const objs=canvas.getActiveObjects(); objs.forEach(o=>canvas.remove(o)); canvas.discardActiveObject(); canvas.renderAll();}}
function dup(){{const o=active(); if(!o)return; o.clone(c=>{{c.set({{left:o.left+30,top:o.top+30}}); canvas.add(c); canvas.setActiveObject(c); canvas.renderAll();}});}}
function flipX(){{const o=active(); if(o){{o.set('flipX',!o.flipX); canvas.renderAll();}}}}
function resetAll(){{ if(confirm('처음 상태로 되돌릴까요?')) load(); }}
document.addEventListener('keydown',e=>{{ if((e.key==='Delete'||e.key==='Backspace')&&active()&&!(active().isEditing)){{del();e.preventDefault();}} }});
const packEl=document.getElementById('pack');
D.pack.forEach(src=>{{const im=document.createElement('img'); im.src=src; im.onclick=()=>fabric.Image.fromURL(src,img=>{{
  const sc=(D.h*0.5)/img.height; img.set({{left:D.w/2-img.width*sc/2,top:D.h/2-img.height*sc/2,scaleX:sc,scaleY:sc,cornerStyle:'circle',transparentCorners:false,cornerColor:'#FF7A59',borderColor:'#FF7A59'}});
  canvas.add(img); canvas.setActiveObject(img); canvas.renderAll();}}); packEl.appendChild(im);}});
function download(){{
  canvas.discardActiveObject(); canvas.renderAll();
  const url=canvas.toDataURL({{format:'png', multiplier:1/zoom}});
  const a=document.createElement('a'); a.href=url; a.download=D.name+'_edit.png'; document.body.appendChild(a); a.click(); a.remove();
}}
</script></body></html>"""
