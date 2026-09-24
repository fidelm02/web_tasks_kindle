/**
 * WhatsApp Baileys Bridge para Kindle Tasks Pro Portal
 * 
 * Se conecta a WhatsApp Web vía multi-device protocol,
 * detecta audios y mensajes en el grupo "Chismoso",
 * descarga el buffer de audio y lo envía al endpoint de FastAPI (8090).
 * Recibe la respuesta interpretada por Gemini y la envía al grupo.
 */

import baileys from '@whiskeysockets/baileys';
const makeWASocket = typeof baileys.default === 'function' ? baileys.default : (typeof baileys === 'function' ? baileys : baileys.makeWASocket);
const DisconnectReason = baileys.DisconnectReason || baileys.default?.DisconnectReason;
const useMultiFileAuthState = baileys.useMultiFileAuthState || baileys.default?.useMultiFileAuthState;
const downloadMediaMessage = baileys.downloadMediaMessage || baileys.default?.downloadMediaMessage;
import pino from 'pino';
import qrcode from 'qrcode-terminal';
import axios from 'axios';
import { Boom } from '@hapi/boom';
import path from 'path';
import fs from 'fs';
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

  const sock = makeWASocket({
    auth: state,
    logger,
    printQRInTerminal: false, // Manejamos el QR manualmente para qrcode-terminal y Portal
    browser: ['KindleTasksPro', 'Chrome', '120.0.0'],
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
      const userJid = sock.user?.id || 'Desconocido';
      console.log(`\n✓ [WhatsApp Bridge] ¡Conectado exitosamente como: ${userJid}!`);
      console.log(`✓ Escuchando mensajes en el grupo "${TARGET_GROUP_NAME}"...\n`);
      await notifyPortalStatus(true, null, userJid.split(':')[0]);
    }
  });

  sock.ev.on('messages.upsert', async ({ messages, type }) => {
    if (type !== 'notify') return;

    for (const msg of messages) {
      // Ignorar mensajes enviados por el bot mismo si no vienen de la app móvil
      if (!msg.message) continue;

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
            groupName = meta.subject || '';
            groupMetaCache.set(remoteJid, groupName);
          } catch (e) {
            continue;
          }
        }

        // Si no es el grupo "Chismoso", ignoramos el mensaje
        if (!groupName.toLowerCase().includes(TARGET_GROUP_NAME)) {
          continue;
        }
      } else {
        // Ignorar chats individuales para respetar privacidad y consumir solo Chismoso
        continue;
      }

      const senderPhone = (msg.key.participant || remoteJid).split('@')[0];
      const pushName = msg.pushName || 'Usuario';

      console.log(`[WhatsApp] Mensaje detectado en grupo "${groupName}" de ${pushName} (${senderPhone})`);

      // Detectar tipo de contenido: Audio o Texto
      const msgContent = msg.message;
      const isAudio = Boolean(msgContent.audioMessage);
      const isText = Boolean(msgContent.conversation || msgContent.extendedTextMessage?.text);

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
          continue;
        }
      } else if (isText) {
        payload.text_content = msgContent.conversation || msgContent.extendedTextMessage?.text || '';
      } else {
        // Tipo de mensaje no manejado (sticker, imagen, etc.)
        continue;
      }

      // Enviar al webhook de FastAPI para interpretación con Gemini y ejecución
      try {
        console.log(`[WhatsApp] Enviando a Portal Webhook (${payload.message_type})...`);
        const response = await axios.post(PORTAL_WEBHOOK_URL, payload, { timeout: 45000 });
        const result = response.data;

        if (result && result.reply) {
          console.log(`[WhatsApp] Respondiendo al grupo: "${result.reply}"`);
          await sock.sendMessage(remoteJid, { text: result.reply }, { quoted: msg });
        }
      } catch (webhookErr) {
        console.error('[WhatsApp] Error al invocar webhook:', webhookErr.message);
        try {
          await sock.sendMessage(
            remoteJid,
            { text: '⚠️ Ocurrió un error al procesar el audio con la IA. Por favor intenta de nuevo.' },
            { quoted: msg }
          );
        } catch (e) {}
      }
    }
  });

  return sock;
}

// Iniciar conexión
connectToWhatsApp().catch(err => {
  console.error('[WhatsApp Bridge Fatal Error]:', err);
});
