/**
 * WhatsApp Baileys Bridge para Kindle Tasks Pro Portal
 * 
 * Se conecta a WhatsApp Web vía multi-device protocol,
 * detecta audios y mensajes en el grupo "Chismoso",
 * descarga el buffer de audio y lo envía al endpoint de FastAPI (8090).
 * Recibe la respuesta interpretada por Gemini y la envía al grupo.
 */

import nodeCrypto from 'node:crypto';
if (!globalThis.crypto) {
  globalThis.crypto = nodeCrypto.webcrypto || nodeCrypto;
}

import makeWASocket, {
  DisconnectReason,
  useMultiFileAuthState,
  downloadMediaMessage,
  fetchLatestBaileysVersion,
  Browsers,
} from '@whiskeysockets/baileys';
import pino from 'pino';
import qrcode from 'qrcode-terminal';
import axios from 'axios';
import { Boom } from '@hapi/boom';
import path from 'path';
import fs from 'fs';
import http from 'node:http';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const PORTAL_WEBHOOK_URL = process.env.PORTAL_WEBHOOK_URL || 'http://127.0.0.1:8090/api/whatsapp/webhook';
const PORTAL_STATUS_URL = process.env.PORTAL_STATUS_URL || 'http://127.0.0.1:8090/api/whatsapp/status/update';
const TARGET_GROUP_NAME = (process.env.TARGET_GROUP_NAME || 'Chismoso').toLowerCase();
const AUTH_DIR = path.join(__dirname, 'auth_info_baileys');

if (!fs.existsSync(AUTH_DIR)) {
  fs.mkdirSync(AUTH_DIR, { recursive: true });
}

// Logger silencioso para no saturar la salida
const logger = pino({ level: 'warn' });

// Cache de nombres de grupos para evitar consultas repetitivas
const groupMetaCache = new Map();
// Cache de IDs de mensajes enviados por el bot para evitar bucles
const botSentMsgIds = new Set();

// Socket activo y JID objetivo para mensajes proactivos (ej. Cron de recordatorios)
let activeSock = null;
let targetGroupJid = process.env.TARGET_GROUP_JID || '120363428629349624@g.us';
const PUSH_SERVER_PORT = process.env.PUSH_SERVER_PORT || 8095;
let pushServerStarted = false;

async function notifyPortalStatus(connected, qrCode = null, phone = null) {
  try {
    const formData = new URLSearchParams();
    formData.append('connected', connected ? 'true' : 'false');
    if (qrCode) formData.append('qr_code', qrCode);
    if (phone) formData.append('phone', phone);

    await axios.post(PORTAL_STATUS_URL, formData, {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      timeout: 3000
    });
  } catch (err) {
    // Silencioso si el portal se está reiniciando
  }
}

async function connectToWhatsApp() {
  const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR);

  let version = [2, 3000, 1015901307];
  try {
    if (typeof fetchLatestBaileysVersion === 'function') {
      const v = await fetchLatestBaileysVersion();
      if (v?.version) version = v.version;
    }
  } catch (e) {}

  const browserInfo = Browsers && typeof Browsers.ubuntu === 'function'
    ? Browsers.ubuntu('Chrome')
    : ['Ubuntu', 'Chrome', '20.0.04'];

  const sock = makeWASocket({
    version,
    auth: state,
    logger,
    printQRInTerminal: false,
    browser: browserInfo,
    generateHighQualityLinkPreview: false,
    syncFullHistory: false
  });

  sock.ev.on('creds.update', saveCreds);

  sock.ev.on('connection.update', async (update) => {
    const { connection, lastDisconnect, qr } = update;

    if (qr) {
      console.log('\n=============================================================');
      console.log(' ESCANEA ESTE CÓDIGO QR DESDE TU WHATSAPP (GRUPO CHISMOSO)   ');
      console.log(' Dispositivos Vinculados -> Vincular un dispositivo          ');
      console.log('=============================================================\n');
      qrcode.generate(qr, { small: true });
      await notifyPortalStatus(false, qr, null);
    }

    if (connection === 'close') {
      const statusCode = (lastDisconnect?.error instanceof Boom) 
        ? lastDisconnect.error.output?.statusCode 
        : null;
      const shouldReconnect = statusCode !== DisconnectReason.loggedOut;
      
      activeSock = null;
      console.log(`[WhatsApp Bridge] Conexión cerrada (Código: ${statusCode}). Reconectar: ${shouldReconnect}`);
      await notifyPortalStatus(false, null, null);

      if (shouldReconnect) {
        setTimeout(connectToWhatsApp, 5000);
      } else {
        console.log('[WhatsApp Bridge] Sesión cerrada permanentemente. Limpiando credenciales para nuevo QR...');
        fs.rmSync(AUTH_DIR, { recursive: true, force: true });
        setTimeout(connectToWhatsApp, 3000);
      }
    } else if (connection === 'open') {
      activeSock = sock;
      const userJid = sock.user?.id || 'Desconocido';
      console.log(`\n✓ [WhatsApp Bridge] ¡Conectado exitosamente como: ${userJid}!`);
      console.log(`✓ Escuchando mensajes en el grupo "${TARGET_GROUP_NAME}"...\n`);
      await notifyPortalStatus(true, null, userJid.split(':')[0]);

      // Intentar auto-descubrir el JID del grupo Chismoso
      try {
        const groups = await sock.groupFetchAllParticipating();
        for (const [gJid, meta] of Object.entries(groups)) {
          if (meta?.subject) groupMetaCache.set(gJid, meta.subject);
          if ((meta?.subject || '').toLowerCase().includes(TARGET_GROUP_NAME)) {
            targetGroupJid = gJid;
            console.log(`✓ [WhatsApp Bridge] Grupo Chismoso detectado automáticamente: ${gJid}`);
          }
        }
      } catch (gErr) {
        // Ignorar si la carga inicial de grupos falla
      }
    }
  });

  sock.ev.on('messages.upsert', async ({ messages, type }) => {
    if (type !== 'notify') return;

    for (const msg of messages) {
      if (!msg.message) continue;

      // Ignorar mensajes de protocolo, actualizaciones de estado y reacciones
      if (msg.message.protocolMessage || msg.message.reactionMessage) continue;

      const msgId = msg.key?.id;
      if (msgId && botSentMsgIds.has(msgId)) {
        continue;
      }

      const remoteJid = msg.key.remoteJid || '';
      const isGroup = remoteJid.endsWith('@g.us');

      // Validar si es el grupo objetivo
      let groupName = '';
      if (isGroup) {
        if (groupMetaCache.has(remoteJid)) {
          groupName = groupMetaCache.get(remoteJid);
        } else {
          try {
            const meta = await sock.groupMetadata(remoteJid);
            groupName = meta?.subject || '';
            if (groupName) groupMetaCache.set(remoteJid, groupName);
          } catch (e) {
            console.warn(`[WhatsApp] Metadata del grupo ${remoteJid} pendiente...`);
          }
        }

        // Si no es el grupo "Chismoso", ignoramos el mensaje
        if (!groupName.toLowerCase().includes(TARGET_GROUP_NAME)) {
          continue;
        }
        targetGroupJid = remoteJid;
      } else {
        // Ignorar chats individuales para respetar privacidad y consumir solo Chismoso
        continue;
      }

      const senderPhone = (msg.key.participant || remoteJid).split('@')[0];
      const pushName = msg.pushName || 'Usuario';

      // Desenvolver mensajes efímeros o view-once si aplica
      let msgContent = msg.message;
      if (msgContent?.ephemeralMessage?.message) {
        msgContent = msgContent.ephemeralMessage.message;
      }
      if (msgContent?.viewOnceMessage?.message) {
        msgContent = msgContent.viewOnceMessage.message;
      }
      if (msgContent?.viewOnceMessageV2?.message) {
        msgContent = msgContent.viewOnceMessageV2.message;
      }
      if (msgContent?.documentWithCaptionMessage?.message) {
        msgContent = msgContent.documentWithCaptionMessage.message;
      }

      // Detectar tipo de contenido: Audio o Texto
      const isAudio = Boolean(msgContent.audioMessage);
      const isText = Boolean(msgContent.conversation || msgContent.extendedTextMessage?.text);

      if (!isAudio && !isText) {
        continue;
      }

      console.log(`[WhatsApp] Mensaje detectado en grupo "${groupName}" de ${pushName} (${senderPhone}) [Tipo: ${isAudio ? 'Audio' : 'Texto'}]`);

      // 1. REACCIÓN INMEDIATA: Emoji de "Procesando" (🎧 para audios, ⏳ para texto)
      try {
        await sock.sendMessage(remoteJid, {
          react: {
            text: isAudio ? '🎧' : '⏳',
            key: msg.key,
          },
        });
      } catch (rErr) {
        console.warn('[WhatsApp] Error al enviar reacción de inicio:', rErr.message);
      }

      let payload = {
        sender_name: pushName,
        sender_phone: senderPhone,
        group_name: groupName,
        message_type: isAudio ? 'audio' : 'text',
      };

      if (isAudio) {
        try {
          console.log('[WhatsApp] Descargando audio PTT...');
          const buffer = await downloadMediaMessage(
            msg,
            'buffer',
            {},
            { logger, reuploadRequest: sock.updateMediaMessage }
          );
          payload.audio_base64 = buffer.toString('base64');
          payload.audio_mimetype = msgContent.audioMessage.mimetype || 'audio/ogg; codecs=opus';
        } catch (downloadErr) {
          console.error('[WhatsApp] Error al descargar audio:', downloadErr);
          try {
            await sock.sendMessage(remoteJid, { react: { text: '❌', key: msg.key } });
          } catch (e) {}
          continue;
        }
      } else {
        payload.text_content = msgContent.conversation || msgContent.extendedTextMessage?.text || '';
      }

      // Enviar al webhook de FastAPI para interpretación con Gemini y ejecución
      try {
        console.log(`[WhatsApp] Enviando a Portal Webhook (${payload.message_type})...`);
        const response = await axios.post(PORTAL_WEBHOOK_URL, payload, { timeout: 45000 });
        const result = response.data;

        if (result && result.reply) {
          console.log(`[WhatsApp] Respondiendo al grupo: "${result.reply}"`);
          
          // 2. REACCIÓN DE ÉXITO: Cambiar emoji a ✅
          try {
            await sock.sendMessage(remoteJid, {
              react: {
                text: '✅',
                key: msg.key,
              },
            });
          } catch (rErr) {}

          let sent = null;
          try {
            sent = await sock.sendMessage(remoteJid, { text: result.reply }, { quoted: msg });
          } catch (qErr) {
            console.warn('[WhatsApp] Envío con quote a grupo falló, intentando sin quote:', qErr.message);
            try {
              sent = await sock.sendMessage(remoteJid, { text: result.reply });
            } catch (plainErr) {
              console.warn('[WhatsApp] Envío a grupo falló, enviando directo al usuario:', plainErr.message);
              const userJid = msg.key.participant || (senderPhone.includes('@') ? senderPhone : `${senderPhone}@s.whatsapp.net`);
              sent = await sock.sendMessage(userJid, { text: `[Grupo Chismoso] ${result.reply}` });
            }
          }

          if (sent?.key?.id) {
            botSentMsgIds.add(sent.key.id);
            if (botSentMsgIds.size > 200) {
              const first = botSentMsgIds.values().next().value;
              botSentMsgIds.delete(first);
            }
          }
        }

        // 3. ENVÍO DE DOCUMENTO ADJUNTO (PDF / TXT) SI FUE GENERADO POR LA IA
        if (result && result.attachment && result.attachment.file_path) {
          const att = result.attachment;
          try {
            if (fs.existsSync(att.file_path)) {
              console.log(`[WhatsApp] Despachando adjunto (${att.file_name || 'documento'}) a ${remoteJid}...`);
              const fileBuffer = fs.readFileSync(att.file_path);
              const mime = att.mimetype || (att.file_path.endsWith('.pdf') ? 'application/pdf' : 'text/plain');
              const fileName = att.file_name || path.basename(att.file_path);
              const caption = att.caption || '';

              let docMsg = null;
              try {
                docMsg = await sock.sendMessage(
                  remoteJid,
                  {
                    document: fileBuffer,
                    mimetype: mime,
                    fileName: fileName,
                    caption: caption,
                  },
                  { quoted: msg }
                );
              } catch (qDocErr) {
                console.warn('[WhatsApp] Envío de adjunto con quote falló, reintentando directo:', qDocErr.message);
                docMsg = await sock.sendMessage(
                  remoteJid,
                  {
                    document: fileBuffer,
                    mimetype: mime,
                    fileName: fileName,
                    caption: caption,
                  }
                );
              }

              if (docMsg?.key?.id) {
                botSentMsgIds.add(docMsg.key.id);
              }
              console.log(`✓ [WhatsApp] Adjunto ${fileName} enviado con éxito al chat.`);
            } else {
              console.warn(`[WhatsApp] Archivo adjunto no encontrado en disco: ${att.file_path}`);
            }
          } catch (attErr) {
            console.error('[WhatsApp] Error al despachar archivo adjunto:', attErr.message);
          }
        }
      } catch (webhookErr) {
        console.error('[WhatsApp] Error al invocar webhook:', webhookErr.message);
        try {
          await sock.sendMessage(remoteJid, { react: { text: '❌', key: msg.key } });
        } catch (e) {}
        try {
          await sock.sendMessage(
            remoteJid,
            { text: '⚠️ Ocurrió un error al procesar el audio con la IA. Por favor intenta de nuevo.' }
          );
        } catch (e) {}
      }
    }
  });

  return sock;
}

/**
 * Microservidor HTTP local para recibir órdenes de despacho proactivas
 * (por ejemplo, el Cron de las 6:00 AM para recordatorios de Fidel, Lau y Martha).
 */
function startPushServer() {
  if (pushServerStarted) return;
  pushServerStarted = true;

  const server = http.createServer(async (req, res) => {
    res.setHeader('Content-Type', 'application/json');

    if (req.method === 'GET' && req.url === '/api/status') {
      res.writeHead(200);
      return res.end(JSON.stringify({
        status: 'ok',
        connected: Boolean(activeSock && activeSock.user),
        targetGroupJid,
        user: activeSock?.user?.id || null,
      }));
    }

    if (req.method === 'POST' && req.url === '/api/send') {
      let body = '';
      req.on('data', chunk => { body += chunk; });
      req.on('end', async () => {
        try {
          const data = JSON.parse(body || '{}');
          const text = data.text;
          const attachment = data.attachment;
          const destJid = data.jid || targetGroupJid;

          if (!text && !attachment) {
            res.writeHead(400);
            return res.end(JSON.stringify({ error: 'El campo text o attachment es requerido' }));
          }
          if (!activeSock) {
            res.writeHead(503);
            return res.end(JSON.stringify({ error: 'WhatsApp Bridge no está conectado aún' }));
          }

          let sentId = null;
          if (text) {
            console.log(`[WhatsApp Push] Despachando mensaje proactivo a ${destJid}...`);
            const sent = await activeSock.sendMessage(destJid, { text });
            if (sent?.key?.id) {
              botSentMsgIds.add(sent.key.id);
              sentId = sent.key.id;
            }
          }

          if (attachment && attachment.file_path && fs.existsSync(attachment.file_path)) {
            console.log(`[WhatsApp Push] Despachando adjunto proactivo ${attachment.file_name || 'documento'} a ${destJid}...`);
            const fileBuffer = fs.readFileSync(attachment.file_path);
            const mime = attachment.mimetype || (attachment.file_path.endsWith('.pdf') ? 'application/pdf' : 'text/plain');
            const fileName = attachment.file_name || path.basename(attachment.file_path);
            const docSent = await activeSock.sendMessage(destJid, {
              document: fileBuffer,
              mimetype: mime,
              fileName: fileName,
              caption: attachment.caption || '',
            });
            if (docSent?.key?.id) {
              botSentMsgIds.add(docSent.key.id);
              sentId = sentId || docSent.key.id;
            }
          }

          res.writeHead(200);
          return res.end(JSON.stringify({ status: 'ok', id: sentId }));
        } catch (err) {
          console.error('[WhatsApp Push Error]:', err.message);
          res.writeHead(500);
          return res.end(JSON.stringify({ error: err.message }));
        }
      });
      return;
    }

    res.writeHead(404);
    res.end(JSON.stringify({ error: 'Ruta no encontrada' }));
  });

  server.listen(PUSH_SERVER_PORT, '127.0.0.1', () => {
    console.log(`✓ [WhatsApp Bridge Push Server] Escuchando en http://127.0.0.1:${PUSH_SERVER_PORT}`);
  });
}

// Iniciar servidor push local para el cron
startPushServer();

// Iniciar conexión Baileys
connectToWhatsApp().catch(err => {
  console.error('[WhatsApp Bridge Fatal Error]:', err);
});

