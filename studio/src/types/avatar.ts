export type AvatarPersonaId = 
  | 'cybernetic-android' // Mark-VII Cybernetic AI (Cyan/Blue Hologram, Ocular HUD)
  | 'futuristic-female'  // Athena AI (Amethyst/Rose-Gold, Concentric Halo, Elegant Matrix)
  | 'space-commander'    // Titan Commander (Amber/Gold Tactical Mesh, Reinforced Hex Chassis)
  | 'energy-orb'         // Quantum Core (Emerald/Pure Plasma Sphere, Oscillating Singularity)
  | 'custom-companion';  // User's Favorite Person / Living Photo Hologram

export type VoiceGender = 'male' | 'female' | 'neutral';
export type VoiceAccent = 'british' | 'us' | 'bengali';
export type CompanionTemperament = 'architect' | 'ironman_jarvis' | 'empathetic_copilot' | 'warm_mentor' | 'devoted_companion';
export type HologramMode = 'cyber' | 'living_human';

export interface AvatarSettings {
  personaId: AvatarPersonaId;
  name: string;
  gender: VoiceGender;
  pitch: number;    // 0.8 to 1.3
  rate: number;     // 0.8 to 1.3
  accent: VoiceAccent;
  temperament: CompanionTemperament;
  soundEnabled: boolean;
  hologramMode: HologramMode;
  customPhotoUrl?: string;
  customPhotoName?: string;
  relationshipArchetype?: string; // e.g. "Mother", "Partner", "Mentor", "Guardian Angel", "Chief of Staff"
  eyeColor?: string; // hex
  glowColor?: string; // hex
}

export const DEFAULT_AVATAR_SETTINGS: AvatarSettings = {
  personaId: 'cybernetic-android',
  name: 'JARVIS Mark-VII',
  gender: 'male',
  pitch: 1.0,
  rate: 1.05,
  accent: 'british',
  temperament: 'ironman_jarvis',
  soundEnabled: true,
  hologramMode: 'cyber',
  relationshipArchetype: 'AI Chief of Staff',
  eyeColor: '#00f0ff',
  glowColor: '#00f0ff',
};

export const AVATAR_PERSONAS = [
  {
    id: 'cybernetic-android' as AvatarPersonaId,
    nameBn: 'জার্ভিস মার্ক-৭ (সাইবারনেটিক কোর)',
    nameEn: 'JARVIS Mark-VII (Cybernetic Core)',
    badge: 'Iron Man Canonical',
    descriptionBn: 'সায়ান ও ব্লু ক্রিস্টালাইন হলো-মেটাবলিজম, অকুলার ট্র্যাকার ও আর্ক রিঅ্যাক্টর হার্ট।',
    descriptionEn: 'Cyan & blue crystalline holo-mesh with ocular tracker and rotary arc reactor heart.',
    primaryColor: '#00f0ff',
    glowColor: 'rgba(0, 240, 255, ',
    accentColor: '#3b82f6',
    defaultGender: 'male' as VoiceGender,
    defaultPitch: 1.0,
    defaultRate: 1.05,
    defaultAccent: 'british' as VoiceAccent,
  },
  {
    id: 'futuristic-female' as AvatarPersonaId,
    nameBn: 'এথিনা এআই (আম্যাথিস্ট নিউরাল মেট্রিক্স)',
    nameEn: 'Athena AI (Amethyst Neural Matrix)',
    badge: 'Celestial Architecture',
    descriptionBn: 'ভায়োলেট ও রোজ-গোল্ড হলো-ফিলামেন্ট, ডবল কনসেন্ট্রিক সেলেস্টিয়াল হ্যালো ক্রাউন ও স্মুথ পারফেকশন।',
    descriptionEn: 'Violet & rose-gold holo-filaments with dual celestial halo crown and harmonic symmetry.',
    primaryColor: '#d946ef',
    glowColor: 'rgba(217, 70, 239, ',
    accentColor: '#f43f5e',
    defaultGender: 'female' as VoiceGender,
    defaultPitch: 1.15,
    defaultRate: 1.02,
    defaultAccent: 'us' as VoiceAccent,
  },
  {
    id: 'space-commander' as AvatarPersonaId,
    nameBn: 'টাইটান কমান্ডার (ট্যাকটিকাল গোল্ড মেস)',
    nameEn: 'Titan Commander (Tactical Gold Mesh)',
    badge: 'Mission Governor',
    descriptionBn: 'অ্যাম্বার গোল্ড হেক্সাগোনাল ডিফেন্স গ্রিড, রিইনফোর্সড জলাইন এবং ডিপ স্পেস টেলিমেট্রি ক্রসহেয়ার।',
    descriptionEn: 'Amber gold hexagonal defense grid with reinforced jawline and telemetry HUD crosshairs.',
    primaryColor: '#f59e0b',
    glowColor: 'rgba(245, 158, 11, ',
    accentColor: '#ea580c',
    defaultGender: 'male' as VoiceGender,
    defaultPitch: 0.88,
    defaultRate: 0.98,
    defaultAccent: 'british' as VoiceAccent,
  },
  {
    id: 'energy-orb' as AvatarPersonaId,
    nameBn: 'কোয়ান্টাম কোর (এমারেল্ড প্লাজমা স্ফিয়ার)',
    nameEn: 'Quantum Core (Emerald Plasma Singularity)',
    badge: 'Abstract Singularity',
    descriptionBn: '৪-লেয়ার পালসিং কোয়ান্টাম প্লাজমা, ইলেকট্রন অরবিটিং ক্লাউড ও হারমোনিক সাইন ওয়েভ এনার্জি।',
    descriptionEn: '4-layer oscillating quantum plasma sphere with electron swarm and harmonic wave vortex.',
    primaryColor: '#10b981',
    glowColor: 'rgba(16, 185, 129, ',
    accentColor: '#06b6d4',
    defaultGender: 'neutral' as VoiceGender,
    defaultPitch: 1.08,
    defaultRate: 1.08,
    defaultAccent: 'us' as VoiceAccent,
  },
  {
    id: 'custom-companion' as AvatarPersonaId,
    nameBn: 'প্রিয় মানুষ (লিভিং ফটো হলোগ্রাম)',
    nameEn: 'Favorite Person (Living Photo Hologram)',
    badge: 'Deep Emotional Anchor',
    descriptionBn: 'আপনার মা, স্ত্রী, প্রিয় মানুষ বা মেন্টরের ছবি আপলোড করুন—হলোগ্রাফিক গ্লো ও প্রাকৃতিক মুভমেন্ট সহ জীবন্ত হয়ে উঠবে।',
    descriptionEn: 'Upload personal photo of your loved one, mother, partner or mentor with glowing hologram contour.',
    primaryColor: '#38bdf8',
    glowColor: 'rgba(56, 189, 248, ',
    accentColor: '#ec4899',
    defaultGender: 'female' as VoiceGender,
    defaultPitch: 1.05,
    defaultRate: 1.0,
    defaultAccent: 'us' as VoiceAccent,
  },
];
