<?php
/**
 * CompiTek – Versand des Anfrage-Formulars (kontakt.html)
 *
 * Prüft die Angaben und schickt sie als E-Mail an EMPFAENGER.
 * Voraussetzung beim Webhoster: PHP 7.0 oder neuer mit mbstring
 * und funktionierender mail()-Funktion (bei deutschen Hostern üblich).
 */
declare(strict_types=1);

// ------------------------- Einstellungen -------------------------
const EMPFAENGER  = 'info@compitek.de';        // hier kommen die Anfragen an
const ABSENDER    = 'webformular@compitek.de'; // muss zur eigenen Domain gehören
const DANKE_SEITE = 'danke.html';
// -----------------------------------------------------------------

mb_internal_encoding('UTF-8');
date_default_timezone_set('Europe/Berlin');

// Auswahlmöglichkeiten (Werte müssen zu kontakt.html passen)
$GERAETE = [
    'pc' => 'PC bzw. Desktop-Computer',
    'laptop' => 'Laptop / Notebook',
    'smartphone' => 'Smartphone / Handy',
    'drucker' => 'Drucker',
    'sonstiges' => 'Sonstiges (bitte unten kurz beschreiben)',
];
$ANLIEGEN = [
    'beratung' => 'Ich brauche Hilfe / Beratung',
    'win11' => 'Ich benötige ein Upgrade auf Windows 11',
    'tot_monitor' => 'PC / Notebook und Monitor komplett tot – keine LED leuchtet, kein Bild, kein Ton',
    'tot' => 'PC / Notebook komplett tot – keine LED leuchtet, kein Bild, kein Ton',
    'monitor' => 'Monitor / Bildschirm schwarz – keine LED leuchtet',
    'startet_nicht' => 'PC / Notebook geht an bzw. leuchtet, aber Windows startet nicht',
    'langsam' => 'PC / Notebook ist langsam, wird heiß, stürzt ab oder der Mauszeiger friert ein',
    'virus' => 'Ich vermute eine Schadsoftware / einen Virus auf meinem Computer',
    'update' => 'Es wurde ein neues Update, eine Software oder ein Treiber installiert',
    'aufraeumtool' => 'Es wurde ein Aufräumtool (z. B. CCleaner) oder eine neue Antivirus-Software installiert',
    'beschaedigt' => 'Das Gerät wurde beschädigt (Sturz, Flüssigkeit o. Ä.)',
    'sonstiges' => 'Sonstiges (bitte unten kurz beschreiben)',
];
$ALTER = [
    'bis5' => 'bis zu 5 Jahre',
    '5bis10' => '5–10 Jahre',
    'ueber10' => 'älter als 10 Jahre',
    'unbekannt' => 'weiß ich nicht',
];
$WINDOWS = [
    '11' => 'Windows 11',
    '10' => 'Windows 10',
    'aelter' => 'Windows 8 / 7 / Vista / XP / 2000 / 98 / 95 / DOS',
    'unbekannt' => 'weiß ich nicht',
];
$HINWEISE = [
    'daten' => 'Es sind wichtige Daten auf dem Gerät',
    'backup' => 'Ich habe eine Datensicherung',
    'passwort' => 'Ich habe das Passwort für mein (Microsoft-)E-Mail-Konto',
    'lizenz_windows' => 'Ich habe den Lizenzcode für Windows',
    'lizenz_office' => 'Ich habe den Lizenzcode für Microsoft Office',
    'bitlocker' => 'Die Festplatte ist (evtl.) verschlüsselt, z. B. mit BitLocker',
];

if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'POST') {
    header('Location: kontakt.html', true, 303);
    exit;
}

/** Einzeiliges Feld: ohne Steuerzeichen (verhindert u. a. Header-Injection), gekürzt */
function textfeld(string $name, int $max): string
{
    $wert = $_POST[$name] ?? '';
    if (!is_string($wert)) {
        return '';
    }
    $wert = preg_replace('/[\x00-\x1F\x7F]+/u', ' ', $wert) ?? '';
    return trim(mb_substr($wert, 0, $max));
}

/** Mehrzeiliges Feld: Zeilenumbrüche bleiben, sonstige Steuerzeichen fliegen raus */
function textblock(string $name, int $max): string
{
    $wert = $_POST[$name] ?? '';
    if (!is_string($wert)) {
        return '';
    }
    $wert = str_replace(["\r\n", "\r"], "\n", $wert);
    $wert = preg_replace('/[\x00-\x08\x0B-\x1F\x7F]+/u', '', $wert) ?? '';
    return trim(mb_substr($wert, 0, $max));
}

/** Angekreuzte Kästchen: nur bekannte Werte, Reihenfolge wie im Formular */
function auswahl(string $name, array $optionen): array
{
    $werte = $_POST[$name] ?? [];
    if (!is_array($werte)) {
        $werte = [$werte];
    }
    $werte = array_filter($werte, 'is_string');
    return array_intersect_key($optionen, array_flip($werte));
}

/** Auswahlknopf (radio): bekannter Wert oder leer */
function einzelauswahl(string $name, array $optionen): string
{
    $wert = $_POST[$name] ?? '';
    return (is_string($wert) && isset($optionen[$wert])) ? $optionen[$wert] : '';
}

/** Einfache Rückmeldeseite im Stil der Website */
function zeige_seite(string $titel, array $punkte, int $status): void
{
    http_response_code($status);
    header('Content-Type: text/html; charset=UTF-8');
    $t = htmlspecialchars($titel, ENT_QUOTES, 'UTF-8');
    $liste = '';
    foreach ($punkte as $punkt) {
        $liste .= '<li>' . htmlspecialchars($punkt, ENT_QUOTES, 'UTF-8') . '</li>';
    }
    echo <<<HTML
<!doctype html>
<html lang="de">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="robots" content="noindex">
  <title>{$t} | CompiTek</title>
  <link rel="icon" href="favicon.svg" type="image/svg+xml">
  <link rel="stylesheet" href="assets/css/style.css">
</head>
<body>
<main id="inhalt">
  <section class="page-hero">
    <div class="container">
      <p class="breadcrumb"><a href="index.html">Start</a> › <a href="kontakt.html">Kontakt</a></p>
      <h1>{$t}</h1>
    </div>
  </section>
  <section class="section">
    <div class="container prose">
      <div class="form-error"><ul>{$liste}</ul></div>
      <p><a class="btn btn-primary" href="kontakt.html#formular" onclick="history.back(); return false;">Zurück zum Formular</a></p>
      <p>Oder rufen Sie einfach an: <a href="tel:+4942037456144"><strong>04203&nbsp;7456144</strong></a></p>
    </div>
  </section>
</main>
</body>
</html>
HTML;
}

// Spam-Falle: Dieses Feld ist für Menschen unsichtbar. Ist es ausgefüllt,
// war ein Roboter am Werk – wir tun so, als wäre alles gut, senden aber nichts.
if (textfeld('website', 200) !== '') {
    header('Location: ' . DANKE_SEITE, true, 303);
    exit;
}

$name      = textfeld('name', 100);
$telefon   = textfeld('telefon', 50);
$email     = textfeld('email', 150);
$modell    = textfeld('modell', 150);
$nachricht = textblock('nachricht', 5000);
$geraete   = auswahl('geraet', $GERAETE);
$anliegen  = auswahl('anliegen', $ANLIEGEN);
$hinweise  = auswahl('hinweise', $HINWEISE);
$alter     = einzelauswahl('alter', $ALTER);
$windows   = einzelauswahl('windows', $WINDOWS);

$fehler = [];
if (!empty($_POST['roboter'])) {
    $fehler[] = 'Sie haben angekreuzt, ein Spam-Roboter zu sein. Falls nicht, entfernen Sie bitte dieses Häkchen.';
}
if (!$geraete) {
    $fehler[] = 'Bitte kreuzen Sie mindestens ein Gerät an.';
}
if (!$anliegen) {
    $fehler[] = 'Bitte setzen Sie mindestens ein Häkchen bei „Worum geht es?“.';
}
if ((isset($geraete['sonstiges']) || isset($anliegen['sonstiges'])) && $nachricht === '') {
    $fehler[] = 'Sie haben „Sonstiges“ angekreuzt – bitte beschreiben Sie das Problem kurz im Nachrichtenfeld.';
}
if ($name === '') {
    $fehler[] = 'Bitte geben Sie Ihren Namen an.';
}
if ($telefon === '' && $email === '') {
    $fehler[] = 'Bitte geben Sie eine Telefonnummer oder E-Mail-Adresse an, damit ich Sie erreichen kann.';
}
if ($email !== '' && !filter_var($email, FILTER_VALIDATE_EMAIL)) {
    $fehler[] = 'Bitte prüfen Sie die E-Mail-Adresse.';
}
if ($telefon !== '' && !preg_match('~^[0-9+()/. -]{5,}$~', $telefon)) {
    $fehler[] = 'Bitte prüfen Sie die Telefonnummer (nur Ziffern, Leerzeichen und + / - erlaubt).';
}

if ($fehler) {
    zeige_seite('Bitte prüfen Sie Ihre Angaben', $fehler, 422);
    exit;
}

// ------------------------- E-Mail zusammenstellen -------------------------

$liste = static function (string $titel, array $eintraege): string {
    if (!$eintraege) {
        return $titel . ": –\n";
    }
    return $titel . ":\n  - " . implode("\n  - ", $eintraege) . "\n";
};

$text  = "Neue Anfrage über das Formular auf compitek.de\n";
$text .= str_repeat('=', 47) . "\n\n";
$text .= 'Name:     ' . $name . "\n";
$text .= 'Telefon:  ' . ($telefon !== '' ? $telefon : '–') . "\n";
$text .= 'E-Mail:   ' . ($email !== '' ? $email : '–') . "\n\n";
$text .= $liste('Gerät', array_values($geraete)) . "\n";
$text .= $liste('Anliegen / Symptome', array_values($anliegen)) . "\n";
$text .= 'Alter des Geräts: ' . ($alter !== '' ? $alter : '–') . "\n";
$text .= 'Windows-Version:  ' . ($windows !== '' ? $windows : '–') . "\n";
$text .= 'Hersteller/Modell: ' . ($modell !== '' ? $modell : '–') . "\n\n";
$text .= $liste('Gut zu wissen', array_values($hinweise)) . "\n";
$text .= "Nachricht:\n" . ($nachricht !== '' ? $nachricht : '–') . "\n\n";
$text .= "--\nGesendet am " . date('d.m.Y \u\m H:i') . " Uhr über compitek.de/kontakt.html\n";
$text  = wordwrap($text, 200, "\n", false);

$betreff = 'Anfrage über compitek.de von ' . $name;
$kopf = [
    'From: ' . mb_encode_mimeheader('CompiTek Webformular', 'UTF-8', 'B') . ' <' . ABSENDER . '>',
    'MIME-Version: 1.0',
    'Content-Type: text/plain; charset=UTF-8',
    'Content-Transfer-Encoding: 8bit',
];
if ($email !== '') {
    $kopf[] = 'Reply-To: ' . $email; // „Antworten“ geht direkt an die Kundin bzw. den Kunden
}

$gesendet = mail(
    EMPFAENGER,
    mb_encode_mimeheader($betreff, 'UTF-8', 'B'),
    $text,
    implode("\r\n", $kopf),
    '-f' . ABSENDER
);

if (!$gesendet) {
    zeige_seite('Das hat leider nicht geklappt', [
        'Ihre Nachricht konnte gerade nicht versendet werden.',
        'Bitte versuchen Sie es später noch einmal oder rufen Sie einfach an.',
    ], 500);
    exit;
}

header('Location: ' . DANKE_SEITE, true, 303);
exit;
