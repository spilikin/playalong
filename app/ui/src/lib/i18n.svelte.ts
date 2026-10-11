// The app speaks English; triple-clicking "Roks ir dzīvs!" switches it to Latvian (and back). There is
// deliberately no other way in and no hint: it's an Easter egg.

export type Lang = 'en' | 'lv';

const LANG_KEY = 'playalong.lang';

const EN = {
  intro: 'Open a song folder made with the playalong CLI to play a mix with its chords.',
  openFolder: 'Open song folder…',
  dialogTitle: 'Open a song folder',
  recent: 'Recent',
  dropHint: 'You can also drop a song folder onto this window.',
  drop: 'Drop to open the song',
  restart: 'Restart',
  restartTitle: 'Back to the start (Home)',
  play: 'Play',
  pause: 'Pause',
  playTitle: 'Play / pause (Space)',
  cover: 'Cover',
  key: 'Key',
  position: 'Position',
  open: 'Open…',
  mixes: 'Mixes',
  more: 'More',
  noMixes: ['This song has no mixes yet. Render some with ', '.'],
  oldMix: ['This mix was rendered before mixes recorded their timing, so chords may be a little off. Render it again with ', '.'],
  noChords: ['No chords yet. Detect them with ', '.'],
  chords: 'Chords',
  now: 'Now',
  next: 'Next',
  cantPlay: (file: string) => `Can't play ${file}.`,
  light: 'Light appearance',
  dark: 'Dark appearance',
  themeTitle: 'Light / dark',
  countIn: (bars: number) => `count-in · ${bars} bar${bars > 1 ? 's' : ''}`,
  chordsByBar: 'Chords by bar',
  bar: (n: number) => `Bar ${n}`,
  shape: (name: string) => `${name} chord shape`,
  customMix: 'custom mix',
  mixNames: {
    original: ['Original', 'the record as it is'],
    guide: ['Guide', 'guitar 15 dB down'],
    'no-guitar': ['No guitar', 'you play the guitar'],
    'vocals-only': ['Vocals only', 'melody and words'],
    backing: ['Backing', 'no guitar, no vocals'],
    'rhythm-section': ['Rhythm section', 'drums and bass'],
    'drums-only': ['Drums only', 'a musical metronome'],
    'guitar-only': ['Guitar only', 'study the part'],
  } as Record<string, [label: string, blurb: string]>,
};

export type Strings = typeof EN;

const LV: Strings = {
  intro: 'Atver dziesmas mapi, ko izveidojis playalong CLI, un spēlē līdzi miksam ar akordiem.',
  openFolder: 'Atvērt dziesmas mapi…',
  dialogTitle: 'Atvērt dziesmas mapi',
  recent: 'Nesen atvērtās',
  dropHint: 'Dziesmas mapi var arī ievilkt šajā logā.',
  drop: 'Atlaid, lai atvērtu dziesmu',
  restart: 'No sākuma',
  restartTitle: 'Uz sākumu (Home)',
  play: 'Atskaņot',
  pause: 'Pauze',
  playTitle: 'Atskaņot / pauze (atstarpe)',
  cover: 'Albuma vāks',
  key: 'Tonalitāte',
  position: 'Pozīcija',
  open: 'Atvērt…',
  mixes: 'Miksi',
  more: 'Vēl',
  noMixes: ['Šai dziesmai vēl nav miksu. Izveido tos ar ', '.'],
  oldMix: ['Šis miks izveidots, pirms miksi saglabāja savu laiku, tāpēc akordi var nedaudz nesakrist. Izveido to vēlreiz ar ', '.'],
  noChords: ['Akordu vēl nav. Nosaki tos ar ', '.'],
  chords: 'Akordi',
  now: 'Tagad',
  next: 'Nākamais',
  cantPlay: (file: string) => `Nevar atskaņot ${file}.`,
  light: 'Gaišais izskats',
  dark: 'Tumšais izskats',
  themeTitle: 'Gaišs / tumšs',
  countIn: (bars: number) => `ieskaitīšana · ${bars} takt${bars > 1 ? 'i' : 's'}`,
  chordsByBar: 'Akordi pa taktīm',
  bar: (n: number) => `Takts ${n}`,
  shape: (name: string) => `${name} akorda tvēriens`,
  customMix: 'pašu miks',
  mixNames: {
    original: ['Oriģināls', 'ieraksts, kāds tas ir'],
    guide: ['Klusa ģitāra', 'ģitāra 15 dB klusāk'],
    'no-guitar': ['Bez ģitāras', 'ģitāru spēlē tu'],
    'vocals-only': ['Tikai vokāls', 'melodija un vārdi'],
    backing: ['Pavadījums', 'bez ģitāras un vokāla'],
    'rhythm-section': ['Ritma grupa', 'bungas un bass'],
    'drums-only': ['Tikai bungas', 'muzikāls metronoms'],
    'guitar-only': ['Tikai ģitāra', 'iemācies partiju'],
  },
};

export const STRINGS: Record<Lang, Strings> = { en: EN, lv: LV };

function storedLang(): Lang {
  try {
    return localStorage.getItem(LANG_KEY) === 'lv' ? 'lv' : 'en';
  } catch {
    return 'en';
  }
}

export const locale = $state({ lang: storedLang() });
if (typeof document !== 'undefined') document.documentElement.lang = locale.lang;

/** The strings in the current language; read inside `$derived` so labels follow a switch. */
export function strings(): Strings {
  return STRINGS[locale.lang];
}

export function toggleLanguage(): void {
  locale.lang = locale.lang === 'en' ? 'lv' : 'en';
  document.documentElement.lang = locale.lang;
  try {
    localStorage.setItem(LANG_KEY, locale.lang);
  } catch {
    // Without storage the switch lasts until the app closes.
  }
}
