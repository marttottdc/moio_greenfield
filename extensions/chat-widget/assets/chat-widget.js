(function(){
  var g=document.getElementById.bind(document),root=g("moio-chat-widget-root");if(!root)return;
  var shop=root.getAttribute("data-shop"),cid=root.getAttribute("data-customer-id")||null,tn=(window.Shopify&&Shopify.template&&Shopify.template.name)||"";
  if(!shop) return;
  var p=(window.location&&window.location.origin?window.location.origin:"")+"/apps/moio-chat";
  function anon(){var k="moio_chat_anonymous_id";try{var v=sessionStorage.getItem(k);if(!v){v="anon_"+Math.random().toString(36).slice(2)+"_"+Date.now();sessionStorage.setItem(k,v)}return v}catch(_){return"anon_"+Date.now()+"_"+Math.random().toString(36).slice(2)}}
  function sid(v){var k="moio_chat_session_id";try{if(arguments.length){if(v)localStorage.setItem(k,v);else localStorage.removeItem(k)}return localStorage.getItem(k)||""}catch(_){return String(v||"")}}
  function themeCfg(){var e=g("mc-tc");if(!e||!e.textContent)return null;try{var j=JSON.parse(e.textContent);return j&&typeof j==="object"&&!Array.isArray(j)?j:null}catch(_){return null}}
  function cfg(cb){var x=new XMLHttpRequest();x.open("GET",p+"/chat-widget-config?shop="+encodeURIComponent(shop));x.onload=function(){if(x.status!==200)return cb(new Error(String(x.status)));try{var c=JSON.parse(x.responseText);var th=themeCfg();if(th){var en=c.enabled,ws=c.ws_url,k;for(k in th)c[k]=th[k];c.enabled=en;c.ws_url=ws}cb(null,c)}catch(e){cb(e)}};x.onerror=function(){cb(new Error("network"))};x.send()}
  function clamp(v,d,min,max){v=parseInt(v,10);if(isNaN(v))v=d;return Math.max(min,Math.min(max,v))}
  function okUrl(u){u=String(u||"").trim();return /^https?:\/\//i.test(u)?u:""}
  function esc(s){var d=document.createElement("div");d.textContent=String(s||"");return d.innerHTML}
  function norm(s){return String(s||"").replace(/\s+/g," ").trim()}
  var urlRe=/https?:\/\/[^\s]+/g;
  function linkify(s){if(!s)return"";return esc(s).replace(urlRe,function(m){var u=m.replace(/[.,;:)]+$/,"");return'<a class="mc-l" href="'+esc(u)+'" target="_blank" rel="noopener noreferrer">'+esc(u)+'</a>'})}
  function pos(el,po,x,y){el.style.left=el.style.right=el.style.top=el.style.bottom="";if(po==="bottom-left"){el.style.left=x+"px";el.style.bottom=y+"px"}else if(po==="top-right"){el.style.right=x+"px";el.style.top=y+"px"}else if(po==="top-left"){el.style.left=x+"px";el.style.top=y+"px"}else{el.style.right=x+"px";el.style.bottom=y+"px"}}
  function parseRich(c){c=String(c||"").trim();if(!c||c.charAt(0)!=="{")return null;try{var j=JSON.parse(c);return j&&Array.isArray(j.items)?j:null}catch(_){return null}}
  function canShow(c){var a=c.allowed_templates;if(!a||!tn)return true;if(typeof a==="string")a=(a+"").split(/\s*,\s*/).filter(Boolean);if(!a.length)return true;return a.indexOf(tn)!==-1}
  function init(c){
    if(!c.enabled||!canShow(c)) return; root.style.display="";
    var primary=c.primary_color||"#000000",position=c.position||"bottom-right",title=c.title||"Chat",icon=c.bubble_icon||"💬",greet=c.greeting||"Hello! How can we help?",wsUrl=c.ws_url;
    var ox=clamp(c.offset_x,20,0,64),oy=clamp(c.offset_y,20,0,96),bs=clamp(c.bubble_size,56,44,72),ww=clamp(c.window_width,360,280,520),wh=clamp(c.window_height,480,320,760);
    var me=anon(),ws=null,conv=sid()||null,msgs=[],pending=[],queue=[],rt=null,ra=0,open=false,win=null,hR=false,hL=false,wS="disconnected",cr=document.createElement;
    function setStatus(s){wS=s;var el=g("mc-st");if(!el)return;el.textContent=s==="connected"?"Connected":s==="connecting"?"Connecting…":s==="error"?"Error":s==="disconnected"?"Disconnected":s;el.className="mc-st mc-st--"+s}
    function typing(v){var e=g("mc-typing");if(e)e.style.display=v?"block":"none"}
    function add(role,content,rich){msgs.push({role:role,content:content,rich:rich||null});render()}
    function loadHistory(items){
      msgs=(Array.isArray(items)?items:[]).map(function(m){return{role:m&&m.role==="user"?"user":"assistant",content:m&&m.content||"",rich:m&&m.rich_content||parseRich(m&&m.content)}});render()
    }
    function richNode(i){
      var t=String(i.type||"").toLowerCase(),u=okUrl(i.url||i.src||i.href),n;
      if(!u) return null;
      if(t==="image"){n=cr("img");n.className="mc-rich__img";n.src=u;n.alt=String(i.alt||"Image");n.loading="lazy";var lu=okUrl(i.link_url||i.href);if(lu){var a=cr("a");a.className="mc-rich__imgl";a.href=lu;a.target="_blank";a.rel="noopener noreferrer";a.appendChild(n);return a}return n}
      if(t==="link"){n=cr("a");n.className="mc-rich__link";n.href=u;n.target="_blank";n.rel="noopener noreferrer";n.textContent=String(i.text||i.label||u);return n}
      if(t==="button"||t==="cta"){n=cr("a");n.className="mc-rich__btn";n.href=u;n.target="_blank";n.rel="noopener noreferrer";n.textContent=String(i.text||i.label||"Open");return n}
      return null
    }
    function render(){
      var el=g("mc-msgs");if(!el)return;el.innerHTML="";
      msgs.forEach(function(m){
        var d=document.createElement("div"),isUser=m.role==="user"; d.className="mc-msg "+(isUser?"mc-msg--user":"mc-msg--bot");
        var txt=String(m.content||"").trim(); if(txt){var t=cr("div");t.className="mc-msg__text";t.innerHTML=linkify(txt);d.appendChild(t)}
        var it=m.rich&&Array.isArray(m.rich.items)?m.rich.items:null; if(it&&it.length){var w=cr("div");w.className="mc-rich";it.forEach(function(i){var n=richNode(i);if(n)w.appendChild(n)});if(w.childNodes.length)d.appendChild(w)}
        el.appendChild(d)
      });
      el.scrollTop=el.scrollHeight
    }
    function clearRT(){if(rt){clearTimeout(rt);rt=null}}
    function sched(){if(!wsUrl||rt||(navigator&&navigator.onLine===false))return;ra++;var d=Math.min(15000,1000*Math.pow(2,Math.min(ra-1,4)))+Math.floor(Math.random()*350);rt=setTimeout(function(){rt=null;connect()},d)}
    function requestHistory(){if(!ws||ws.readyState!==1||hR)return;hR=true;ws.send(JSON.stringify({action:"get_history",data:{session_id:conv||sid()||null}}))}
    function flush(){if(!hL||!ws||ws.readyState!==1)return;while(queue.length){var q=queue.shift();if(q&&String(q).trim())ws.send(JSON.stringify({action:"send_message",data:{content:q}}))}}
    function sendWS(t){if(!hL||!ws||ws.readyState!==1){queue.push(t);connect();return}ws.send(JSON.stringify({action:"send_message",data:{content:t}}))}
    function connect(){
      if(!wsUrl||(ws&&(ws.readyState===1||ws.readyState===0))||(navigator&&navigator.onLine===false)) return;
      clearRT(); setStatus("connecting"); try{ws=new WebSocket(wsUrl)}catch(_){setStatus("error");return}
      ws.onopen=function(){ra=0;hR=false;hL=false;var sendInit=function(){if(ws&&ws.readyState===1){ws.send(JSON.stringify({action:"init",data:{shop_domain:shop,anonymous_id:me,customer_id:cid,session_id:sid()||null}}))}};setTimeout(sendInit,50)};
      ws.onmessage=function(ev){
        try{
          var m=JSON.parse(ev.data),et=m.event_type,p=m.payload||{};
          if(et==="session_started"){setStatus("connected");conv=(p.session_id!=null&&p.session_id!=="")?p.session_id:(p.conversation_id||conv);if(conv)sid(conv);requestHistory()}
          else if(et==="history"){hL=true;loadHistory(p.messages||[]);if(!msgs.length&&greet)add("assistant",greet);flush()}
          else if(et==="message_received"){var inc=norm(p.content);if(pending.length&&inc&&inc===pending[0])pending.shift();else add("user",p.content)}
          else if(et==="bot_message"){typing(false);add("assistant",p.content,p.rich_content||parseRich(p.content))}
          else if(et==="typing") typing(p.status==="typing");
          else if(et==="error"){typing(false);add("assistant","Sorry, something went wrong. Please try again.")}
        }catch(_){}
      };
      ws.onerror=function(){typing(false);setStatus("error")};
      ws.onclose=function(ev){typing(false);ws=null;setStatus("disconnected");var code=ev&&ev.code;if(code===4000||code===4001||code===4002||code===4003)return; sched()}
    }
    function send(t){t=String(t||"");if(!t.trim())return;add("user",t);var n=norm(t);if(n){pending.push(n);if(pending.length>50)pending=pending.slice(-50)}sendWS(t);typing(true)}
    var b=cr("button"); b.className="mc-bubble"; b.style.background=primary;b.style.color="#fff";b.style.width=bs+"px";b.style.height=bs+"px";b.style.fontSize=Math.max(18,Math.round(bs*.42))+"px";pos(b,position,ox,oy);b.setAttribute("aria-label","Open chat");
    var iu=okUrl(icon); if(iu){var im=cr("img");im.src=iu;im.alt="";im.className="mc-bubble__icon";im.style.width=Math.round(bs*.62)+"px";im.style.height=Math.round(bs*.62)+"px";b.appendChild(im)} else b.textContent=String(icon||"💬");
    function close(){if(win)win.style.display="none";open=false}
    function openWin(){
      if(win){win.style.display="flex";open=true;connect();return}
      win=cr("div");win.className="mc-win mc-win--"+position;win.style.width=ww+"px";win.style.height=wh+"px";win.style.maxWidth="calc(100vw - 16px)";win.style.maxHeight="calc(100vh - 16px)";win.style.position="fixed";pos(win,position,ox,oy+bs+10);
      win.innerHTML='<div class="mc-win__h"><span>'+esc(title)+'</span> <span id="mc-st" class="mc-st mc-st--disconnected" aria-live="polite">Disconnected</span> <button type="button" class="mc-win__close" aria-label="Close">×</button></div><div id="mc-msgs" class="mc-win__msgs"></div><div id="mc-typing" class="mc-typing" style="display:none">Typing...</div><div class="mc-win__inp"><input type="text" class="mc-inp" id="mc-in" placeholder="Type a message..." /></div>';
      document.body.appendChild(win);open=true;      win.querySelector(".mc-win__close").onclick=close;
      win.querySelector("#mc-in").onkeydown=function(e){if(e.key==="Enter"&&!e.shiftKey){e.preventDefault();send(this.value);this.value=""}};
      render();
      connect()
    }
    b.onclick=function(){open?close():openWin()}; document.body.appendChild(b);
    window.addEventListener("online",function(){if(open)connect()}); window.addEventListener("offline",function(){typing(false)});
  }
  cfg(function(e,c){if(!e&&c)init(c)})
})();
