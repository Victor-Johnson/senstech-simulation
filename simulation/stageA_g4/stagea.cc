// Stage A: shared upstream photon field (Protocol s5, Table 5) -> phase-space file at z = 639 mm.
//
//   stagea <geometry.gdml> <spectrum.csv> <n_primaries> <out_prefix> [seed] [threads]
//
// Geometry: GDML written by stagea_geometry.py (source frame: focal spot at z=0, beam along +z,
//   x along the belt, y across). Volume names used here: Object, Belt*, Rail*, Cabinet*, Collimator*,
//   Slit*, Housing*; scoring plane "Plane" (vacuum, 1 um thick) centred at z = 639 mm.
// Source: focal spot uniform square (side from header of spectrum file, default 1 mm); energy sampled from
//   the 1 keV spectrum CSV (columns energy_keV,weight); direction uniform over the rectangle
//   [-ax/2,ax/2] x [-ay/2,ay/2] at z = z_aim (variance reduction: only the cone that can reach the
//   tube-exit collimator is sampled; the represented photon count per mAs is written to the header).
// Output (binary, little endian, one record per photon crossing the plane inside the scored patch):
//   float32 E_keV, x_mm, y_mm, ux, uy, uz, t_ns; uint8 origin, uint8 last_volume
//   origin: 0 primary (never interacted), 1 Rayleigh only, 2 Compton (>=1), 3 fluorescence/secondary photon,
//           4 other.  last_volume: 0 none, 1 Object, 2 Belt, 3 Rail, 4 Cabinet, 5 Collimator/Slit, 6 Housing, 7 other
//   plus <out_prefix>.json with all run parameters and counters.
#include "G4RunManagerFactory.hh"
#include "G4GDMLParser.hh"
#include "G4VUserDetectorConstruction.hh"
#include "G4VUserPrimaryGeneratorAction.hh"
#include "G4VUserActionInitialization.hh"
#include "G4UserSteppingAction.hh"
#include "G4UserTrackingAction.hh"
#include "G4VUserTrackInformation.hh"
#include "G4ParticleGun.hh"
#include "G4Gamma.hh"
#include "G4PhysListFactory.hh"
#include "G4EmParameters.hh"
#include "G4Step.hh"
#include "G4Track.hh"
#include "G4VProcess.hh"
#include "G4SystemOfUnits.hh"
#include "G4AutoLock.hh"
#include "Randomize.hh"
#include <atomic>
#include <chrono>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

namespace {
G4Mutex gMutex = G4MUTEX_INITIALIZER;
std::ofstream gBin;
std::atomic<long> gWritten{0}, gByOrigin[5];
std::vector<double> gE, gCdf;
double gSpot = 1.0 * mm, gAimZ = 100 * mm, gAimX = 7.2 * mm, gAimY = 36 * mm;   // aim rectangle (x along belt)
double gPatchX = 15 * mm, gPatchY = 25 * mm;                                   // scored half-sizes at the plane
const double kPlaneZ = 639 * mm;

uint8_t volCode(const G4String& n) {
  if (n.rfind("Object", 0) == 0) return 1;
  if (n.rfind("Belt", 0) == 0) return 2;
  if (n.rfind("Rail", 0) == 0) return 3;
  if (n.rfind("Cabinet", 0) == 0) return 4;
  if (n.rfind("Collimator", 0) == 0 || n.rfind("Slit", 0) == 0) return 5;
  if (n.rfind("Housing", 0) == 0) return 6;
  return 7;
}

struct Info : G4VUserTrackInformation {
  uint8_t origin = 0, lastVol = 0;
};

struct Det : G4VUserDetectorConstruction {
  G4VPhysicalVolume* w;
  explicit Det(G4VPhysicalVolume* v) : w(v) {}
  G4VPhysicalVolume* Construct() override { return w; }
};

struct Gun : G4VUserPrimaryGeneratorAction {
  G4ParticleGun g{1};
  Gun() { g.SetParticleDefinition(G4Gamma::Definition()); }
  void GeneratePrimaries(G4Event* e) override {
    double u = G4UniformRand();
    size_t i = std::lower_bound(gCdf.begin(), gCdf.end(), u) - gCdf.begin();
    if (i >= gE.size()) i = gE.size() - 1;
    double E = (gE[i] - 0.5 + G4UniformRand()) * keV;                          // uniform within the 1 keV bin
    G4ThreeVector p0((G4UniformRand() - 0.5) * gSpot, (G4UniformRand() - 0.5) * gSpot, 0);
    G4ThreeVector aim((G4UniformRand() - 0.5) * gAimX, (G4UniformRand() - 0.5) * gAimY, gAimZ);
    g.SetParticleEnergy(E); g.SetParticlePosition(p0); g.SetParticleMomentumDirection((aim - p0).unit());
    g.GeneratePrimaryVertex(e);
  }
};

struct Track : G4UserTrackingAction {
  void PreUserTrackingAction(const G4Track* t) override {
    if (t->GetUserInformation()) return;
    auto* inf = new Info;
    if (t->GetParentID() != 0) inf->origin = (t->GetDefinition() == G4Gamma::Definition()) ? 3 : 4;
    const_cast<G4Track*>(t)->SetUserInformation(inf);
  }
};

struct Step : G4UserSteppingAction {
  void UserSteppingAction(const G4Step* s) override {
    auto* t = s->GetTrack();
    if (t->GetDefinition() != G4Gamma::Definition()) return;
    auto* inf = static_cast<Info*>(t->GetUserInformation());
    auto post = s->GetPostStepPoint();
    if (auto* pr = post->GetProcessDefinedStep()) {
      const auto& n = pr->GetProcessName();
      if (n == "Rayl" || n == "compt") {
        if (inf->origin == 0 || inf->origin == 1) inf->origin = (n == "Rayl") ? 1 : 2;
        if (n == "compt" && inf->origin == 1) inf->origin = 2;
        inf->lastVol = volCode(s->GetPreStepPoint()->GetPhysicalVolume()->GetName());
      }
    }
    auto* pv = post->GetPhysicalVolume();
    if (!pv || post->GetStepStatus() != fGeomBoundary || pv->GetName() != "Plane") return;
    const auto& x = post->GetPosition(); const auto& u = post->GetMomentumDirection();
    if (u.z() > 0 && std::abs(x.x()) < gPatchX && std::abs(x.y()) < gPatchY) {
      float rec[7] = {float(post->GetKineticEnergy() / keV), float(x.x() / mm), float(x.y() / mm),
                      float(u.x()), float(u.y()), float(u.z()), float(post->GetGlobalTime() / ns)};
      uint8_t tag[2] = {inf->origin, inf->lastVol};
      G4AutoLock l(&gMutex);
      gBin.write(reinterpret_cast<char*>(rec), sizeof(rec));
      gBin.write(reinterpret_cast<char*>(tag), 2);
      ++gWritten; ++gByOrigin[inf->origin];
    }
    t->SetTrackStatus(fStopAndKill);   // the plane is the end of Stage A
  }
};

struct Actions : G4VUserActionInitialization {
  void Build() const override { SetUserAction(new Gun); SetUserAction(new Track); SetUserAction(new Step); }
};

void readSpectrum(const std::string& f) {
  std::ifstream in(f); std::string line; std::getline(in, line);
  double acc = 0; std::vector<double> w;
  while (std::getline(in, line)) {
    std::stringstream ss(line); std::string a, b;
    std::getline(ss, a, ','); std::getline(ss, b, ',');
    if (a.empty() || b.empty()) continue;
    double e = std::stod(a), v = std::stod(b);
    if (v <= 0) continue;
    gE.push_back(e); acc += v; w.push_back(acc);
  }
  for (double v : w) gCdf.push_back(v / acc);
}
double envd(const char* k, double def) { const char* v = std::getenv(k); return v ? std::stod(v) : def; }
}  // namespace

int main(int argc, char** argv) {
  if (argc < 5) { std::cerr << "usage: stagea geom.gdml spectrum.csv N out_prefix [seed] [threads]\n"; return 1; }
  std::string out = argv[4]; long N = std::stol(argv[3]);
  long seed = argc > 5 ? std::stol(argv[5]) : 1; int threads = argc > 6 ? std::stoi(argv[6]) : 1;
  gSpot = envd("STAGEA_SPOT_MM", 1.0) * mm;
  gAimZ = envd("STAGEA_AIM_Z_MM", 100.0) * mm; gAimX = envd("STAGEA_AIM_X_MM", 7.2) * mm; gAimY = envd("STAGEA_AIM_Y_MM", 36.0) * mm;
  gPatchX = envd("STAGEA_PATCH_HX_MM", 15.0) * mm; gPatchY = envd("STAGEA_PATCH_HY_MM", 25.0) * mm;
  for (auto& c : gByOrigin) c = 0;
  readSpectrum(argv[2]);
  G4Random::setTheSeed(seed);
  G4GDMLParser parser; parser.Read(argv[1], false);
  auto* rm = G4RunManagerFactory::CreateRunManager(threads > 1 ? G4RunManagerType::MT : G4RunManagerType::Serial);
  if (threads > 1) rm->SetNumberOfThreads(threads);
  rm->SetUserInitialization(new Det(parser.GetWorldVolume()));
  G4PhysListFactory f; auto* pl = f.GetReferencePhysList("QGSP_BERT_LIV");
  pl->SetDefaultCutValue(envd("STAGEA_CUT_UM", 10.0) * um);
  rm->SetUserInitialization(pl);
  auto* em = G4EmParameters::Instance(); em->SetFluo(true); em->SetAuger(false); em->SetPixe(false);
  rm->SetUserInitialization(new Actions);
  rm->Initialize();
  gBin.open(out + ".bin", std::ios::binary);
  auto t0 = std::chrono::steady_clock::now();
  rm->BeamOn(N);
  double secs = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
  gBin.close();
  std::ofstream js(out + ".json");
  js << "{\n \"geometry\": \"" << argv[1] << "\",\n \"spectrum\": \"" << argv[2] << "\",\n \"n_primaries\": " << N
     << ",\n \"seed\": " << seed << ",\n \"threads\": " << threads << ",\n \"seconds\": " << secs
     << ",\n \"physics_list\": \"QGSP_BERT_LIV\",\n \"cut_um\": " << envd("STAGEA_CUT_UM", 10.0)
     << ",\n \"focal_spot_mm\": " << gSpot / mm << ",\n \"aim_rect_mm\": [" << gAimX / mm << ", " << gAimY / mm << ", " << gAimZ / mm << "]"
     << ",\n \"patch_half_mm\": [" << gPatchX / mm << ", " << gPatchY / mm << "],\n \"plane_z_mm\": " << kPlaneZ / mm
     << ",\n \"record\": \"<7f2B: E_keV,x_mm,y_mm,ux,uy,uz,t_ns,origin,last_volume\",\n \"written\": " << gWritten.load()
     << ",\n \"by_origin\": [" << gByOrigin[0] << ", " << gByOrigin[1] << ", " << gByOrigin[2] << ", " << gByOrigin[3] << ", " << gByOrigin[4] << "]\n}\n";
  std::cout << "STAGEA done N=" << N << " written=" << gWritten << " seconds=" << secs << std::endl;
  delete rm;
  return 0;
}
