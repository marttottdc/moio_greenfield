(function(){
  var root=document.getElementById("moio-chat-widget-root"); if(!root) return;
  var shop=root.getAttribute("data-shop"),cid=root.getAttribute("data-customer-id")||null,tn=(window.Shopify&&Shopify.template&&Shopify.template.name)||"";
  if(!shop) return;
  var p=(window.location&&window.location.origin?window.location.origin:"")+"/apps/moio-chat";
  function anon(){var k="moio_chat_anonymous_id";try{var v=sessionStorage.getItem(k);if(!v){v="anon_"+Math.random().toString(36).slice(2)+"_"+Date.now();sessionStorage.setItem(k,v)}return v}catch(_){return"anon_"+Date.now()+"_"+Math.random().toString(36).slice(2)}}
  function cfg(cb){var x=new XMLHttpRequest();x.open("GET",p+"/chat-widget-config?shop="+encodeURIComponent(shop));x.onload=function(){if(x.status!==200)return cb(new Error(String(x.status)));try{cb(null,JSON.parse(x.responseText))}catch(e){cb(e)}};x.onerror=function(){cb(new Error("network"))};x.send()}
  function clamp(v,d,min,max){v=parseInt(v,10);if(isNaN(v))v=d;return Math.max(min,Math.min(max,v))}
  function okUrl(u){u=String(u||"").trim();return /^https?:\/\//i.test(u)?u:""}
  function esc(s){var d=document.createElement("div");d.textContent=String(s||"");return d.innerHTML}
  function norm(s){return String(s||"").replace(/\s+/g," ").trim()}
  function pos(el,po,x,y){el.style.left=el.style.right=el.style.top=el.style.bottom="";if(po==="bottom-left"){el.style.left=x+"px";el.style.bottom=y+"px"}else if(po==="top-right"){el.style.right=x+"px";el.style.top=y+"px"}else if(po==="top-left"){el.style.left=x+"px";el.style.top=y+"px"}else{el.style.right=x+"px";el.style.bottom=y+"px"}}
  function parseRich(c){c=String(c||"").trim();if(!c||c.charAt(0)!=="{")return null;try{var j=JSON.parse(c);return j&&Array.isArray(j.items)?j:null}catch(_){return null}}
  function canShow(c){var a=c.allowed_templates; if(!a||!a.length||!tn) return true; return a.indexOf(tn)!==-1}
  function init(c){
    if(!c.enabled||!canShow(c)) return; root.style.display="";
    var primary=c.primary_color||"#000000",position=c.position||"bottom-right",title=c.title||"Chat",icon=c.bubble_icon||"💬",greet=c.greeting||"Hello! How can we help?",wsUrl=c.ws_url;
    var ox=clamp(c.offset_x,20,0,64),oy=clamp(c.offset_y,20,0,96),bs=clamp(c.bubble_size,56,44,72),ww=clamp(c.window_width,360,280,520),wh=clamp(c.window_height,480,320,760);
    var me=anon(),ws=null,conv=null,msgs=[],pending=[],queue=[],rt=null,ra=0,open=false,win=null;
    function typing(v){var e=document.getElementById("moio-chat-typing"); if(e)e.style.display=v?"block":"none"}
    function add(role,content,rich){msgs.push({role:role,content:content,rich:rich||null});render()}
    function richNode(i){
      var t=String(i.type||"").toLowerCase(),u=okUrl(i.url||i.src||i.href),n;
      if(!u) return null;
      if(t==="image"){n=document.createElement("img");n.className="moio-chat-rich__image";n.src=u;n.alt=String(i.alt||"Image");n.loading="lazy";var lu=okUrl(i.link_url||i.href);if(lu){var a=document.createElement("a");a.className="moio-chat-rich__image-link";a.href=lu;a.target="_blank";a.rel="noopener noreferrer";a.appendChild(n);return a}return n}
      if(t==="link"){n=document.createElement("a");n.className="moio-chat-rich__link";n.href=u;n.target="_blank";n.rel="noopener noreferrer";n.textContent=String(i.text||i.label||u);return n}
      if(t==="button"||t==="cta"){n=document.createElement("a");n.className="moio-chat-rich__button";n.href=u;n.target="_blank";n.rel="noopener noreferrer";n.textContent=String(i.text||i.label||"Open");return n}
      return null
    }
    function render(){
      var el=document.getElementById("moio-chat-messages"); if(!el) return; el.innerHTML="";
      msgs.forEach(function(m){
        var d=document.createElement("div"),isUser=m.role==="user"; d.className="moio-chat-message "+(isUser?"moio-chat-message--user":"moio-chat-message--bot");
        var txt=String(m.content||"").trim(); if(txt){var t=document.createElement("div");t.className="moio-chat-message__text";t.textContent=txt;d.appendChild(t)}
        var it=m.rich&&Array.isArray(m.rich.items)?m.rich.items:null; if(it&&it.length){var w=document.createElement("div");w.className="moio-chat-rich";it.forEach(function(i){var n=richNode(i);if(n)w.appendChild(n)});if(w.childNodes.length)d.appendChild(w)}
        el.appendChild(d)
      });
      el.scrollTop=el.scrollHeight
    }
    function clearRT(){if(rt){clearTimeout(rt);rt=null}}
    function sched(){if(!wsUrl||rt||(navigator&&navigator.onLine===false))return;ra++;var d=Math.min(15000,1000*Math.pow(2,Math.min(ra-1,4)))+Math.floor(Math.random()*350);rt=setTimeout(function(){rt=null;connect()},d)}
    function flush(){if(!ws||ws.readyState!==1)return;while(queue.length){var q=queue.shift();if(q&&String(q).trim())ws.send(JSON.stringify({action:"send_message",data:{content:q}}))}}
    function sendWS(t){if(!ws||ws.readyState!==1){queue.push(t);connect();return}ws.send(JSON.stringify({action:"send_message",data:{content:t}}))}
    function connect(){
      if(!wsUrl||(ws&&(ws.readyState===1||ws.readyState===0))||(navigator&&navigator.onLine===false)) return;
      clearRT(); try{ws=new WebSocket(wsUrl)}catch(_){return}
      ws.onopen=function(){ra=0;ws.send(JSON.stringify({action:"init",data:{shop_domain:shop,anonymous_id:me,customer_id:cid}}))};
      ws.onmessage=function(ev){
        try{
          var m=JSON.parse(ev.data),et=m.event_type,p=m.payload||{};
          if(et==="session_started"){if(!conv)add("assistant",greet);conv=p.conversation_id||p.session_id||conv;flush()}
          else if(et==="message_received"){var inc=norm(p.content);if(pending.length&&inc&&inc===pending[0])pending.shift();else add("user",p.content)}
          else if(et==="bot_message"){typing(false);add("assistant",p.content,p.rich_content||parseRich(p.content))}
          else if(et==="typing") typing(p.status==="typing");
          else if(et==="error"){typing(false);add("assistant","Sorry, something went wrong. Please try again.")}
        }catch(_){}
      };
      ws.onerror=function(){typing(false)};
      ws.onclose=function(){typing(false);ws=null;sched()}
    }
    function send(t){t=String(t||"");if(!t.trim())return;add("user",t);var n=norm(t);if(n){pending.push(n);if(pending.length>50)pending=pending.slice(-50)}sendWS(t);typing(true)}
    var b=document.createElement("button"); b.className="moio-chat-bubble"; b.style.background=primary;b.style.color="#fff";b.style.width=bs+"px";b.style.height=bs+"px";b.style.fontSize=Math.max(18,Math.round(bs*.42))+"px";pos(b,position,ox,oy);b.setAttribute("aria-label","Open "+String(title||"chat"));
    var iu=okUrl(icon); if(iu){var im=document.createElement("img");im.src=iu;im.alt="";im.className="moio-chat-bubble__icon-image";im.style.width=Math.round(bs*.62)+"px";im.style.height=Math.round(bs*.62)+"px";b.appendChild(im)} else b.textContent=String(icon||"💬");
    function close(){if(win)win.style.display="none";open=false}
    function openWin(){
      if(win){win.style.display="flex";open=true;return}
      win=document.createElement("div");win.className="moio-chat-window moio-chat-window--"+position;win.style.width=ww+"px";win.style.height=wh+"px";win.style.maxWidth="calc(100vw - 16px)";win.style.maxHeight="calc(100vh - 16px)";win.style.position="fixed";pos(win,position,ox,oy+bs+10);
      win.innerHTML='<div class="moio-chat-window__header">'+esc(title)+' <button type="button" class="moio-chat-window__close" aria-label="Close">×</button></div><div id="moio-chat-messages" class="moio-chat-window__messages"></div><div id="moio-chat-typing" class="moio-chat-typing" style="display:none">Typing...</div><div class="moio-chat-window__input-wrap"><input type="text" class="moio-chat-window__input" id="moio-chat-input" placeholder="Type a message..." /></div>';
      document.body.appendChild(win);open=true;win.querySelector(".moio-chat-window__close").onclick=close;
      win.querySelector("#moio-chat-input").onkeydown=function(e){if(e.key==="Enter"&&!e.shiftKey){e.preventDefault();send(this.value);this.value=""}};
      render()
    }
    b.onclick=function(){open?close():openWin()}; document.body.appendChild(b);
    window.addEventListener("online",connect); window.addEventListener("offline",function(){typing(false)});
    connect()
  }
  cfg(function(e,c){if(!e&&c)init(c)})
})();
