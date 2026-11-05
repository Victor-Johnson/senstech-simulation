// Feasibility test 4: standalone Geant4 app.
//   stagea_spike <geometry.gdml> <mode: trans|scint|mu> <E_keV> <n_events> <out.csv> [seed]
// mu: writes Geant4 mu/rho per process for volume "Object", 10-300 keV (E and N ignored).
// Geometry from GDML (custom alloy mixtures by mass fraction; NIST scintillators).
// Physics: QGSP_BERT_LIV (Livermore EM), production cut 1 um, fluorescence ON, Auger OFF.
// trans: pencil beam along +z through volume "Object"; counts photons entering volume "Plane"
//        and the subset that are unscattered primaries (track 1, E=E0, direction unchanged).
//        Also prints Geant4's own mu (G4EmCalculator, sum of gamma processes) for "Object".
// scint: per-event total energy deposit in volume "Scint" written to out.csv.
#include "G4RunManagerFactory.hh"
#include "G4GDMLParser.hh"
#include "G4VUserDetectorConstruction.hh"
#include "G4VUserPrimaryGeneratorAction.hh"
#include "G4UserSteppingAction.hh"
#include "G4UserEventAction.hh"
#include "G4ParticleGun.hh"
#include "G4Gamma.hh"
#include "G4PhysListFactory.hh"
#include "G4EmParameters.hh"
#include "G4EmCalculator.hh"
#include "G4LogicalVolumeStore.hh"
#include "G4Step.hh"
#include "G4Event.hh"
#include "G4SystemOfUnits.hh"
#include "Randomize.hh"
#include <fstream>
#include <iostream>
#include <chrono>
#include <cmath>

static std::string gMode; static double gE0;
static long gPlaneAll = 0, gPlanePrimary = 0, gScintHit = 0;
static double gEdep = 0; static std::ofstream gOut;

struct Det : G4VUserDetectorConstruction {
  G4VPhysicalVolume* world;
  explicit Det(G4VPhysicalVolume* w) : world(w) {}
  G4VPhysicalVolume* Construct() override { return world; }
};
struct Gun : G4VUserPrimaryGeneratorAction {
  G4ParticleGun g{1};
  Gun() { g.SetParticleDefinition(G4Gamma::Definition()); g.SetParticleEnergy(gE0);
          g.SetParticlePosition({0, 0, -50 * mm}); g.SetParticleMomentumDirection({0, 0, 1}); }
  void GeneratePrimaries(G4Event* e) override { g.GeneratePrimaryVertex(e); }
};
struct Step : G4UserSteppingAction {
  void UserSteppingAction(const G4Step* s) override {
    auto pre = s->GetPreStepPoint(); auto post = s->GetPostStepPoint();
    if (gMode == "trans") {
      if (!post->GetPhysicalVolume()) return;
      if (post->GetStepStatus() == fGeomBoundary && post->GetPhysicalVolume()->GetName() == "Plane"
          && s->GetTrack()->GetDefinition() == G4Gamma::Definition()) {
        ++gPlaneAll;
        auto d = post->GetMomentumDirection();
        if (s->GetTrack()->GetTrackID() == 1 && std::abs(post->GetKineticEnergy() - gE0) < 1e-9 * keV && d.z() > 1 - 1e-12)
          ++gPlanePrimary;
        s->GetTrack()->SetTrackStatus(fStopAndKill);
      }
    } else if (pre->GetPhysicalVolume()->GetName() == "Scint") {
      gEdep += s->GetTotalEnergyDeposit();
    }
  }
};
struct Evt : G4UserEventAction {
  void BeginOfEventAction(const G4Event*) override { gEdep = 0; }
  void EndOfEventAction(const G4Event* e) override {
    if (gMode == "scint" && gEdep > 0) { ++gScintHit; gOut << e->GetEventID() << "," << gEdep / keV << "\n"; }
  }
};

int main(int argc, char** argv) {
  if (argc < 6) { std::cerr << "usage: stagea_spike geom.gdml trans|scint E_keV N out.csv [seed]\n"; return 1; }
  gMode = argv[2]; gE0 = std::stod(argv[3]) * keV; long N = std::stol(argv[4]);
  long seed = argc > 6 ? std::stol(argv[6]) : 1;
  G4Random::setTheSeed(seed);
  G4GDMLParser parser; parser.Read(argv[1], false);
  auto rm = G4RunManagerFactory::CreateRunManager(G4RunManagerType::Serial);
  rm->SetUserInitialization(new Det(parser.GetWorldVolume()));
  G4PhysListFactory f; auto pl = f.GetReferencePhysList("QGSP_BERT_LIV");
  pl->SetDefaultCutValue(1 * um);
  rm->SetUserInitialization(pl);
  auto em = G4EmParameters::Instance(); em->SetFluo(true); em->SetAuger(false); em->SetPixe(false);
  rm->SetUserAction(new Gun); rm->SetUserAction(new Step); rm->SetUserAction(new Evt);
  rm->Initialize();
  gOut.open(argv[5]); if (gMode == "scint") gOut << "event,edep_keV\n";
  if (gMode == "mu") {  // Geant4's own mu/rho
    rm->BeamOn(0);       // physics tables are built at run start, not at Initialize() for volume "Object" on a 1 keV grid 10..300 keV (per process)
    auto mat = G4LogicalVolumeStore::GetInstance()->GetVolume("Object")->GetMaterial();
    double rho = mat->GetDensity() / (g / cm3);
    G4EmCalculator c;
    gOut << "material,density_g_cm3,energy_keV,coherent,incoherent,photoelectric,pair,total_with_coherent\n";
    for (int e = 10; e <= 300; ++e) {
      double E = e * keV, v[4]; const char* pr[4] = {"Rayl", "compt", "phot", "conv"}; double tot = 0;
      for (int i = 0; i < 4; ++i) { v[i] = c.ComputeCrossSectionPerVolume(E, G4Gamma::Definition(), pr[i], mat) * cm / rho; tot += v[i]; }
      gOut << mat->GetName() << "," << rho << "," << e << "," << v[0] << "," << v[1] << "," << v[2] << "," << v[3] << "," << tot << "\n";
    }
    gOut.close(); delete rm; return 0;
  }
  auto t0 = std::chrono::steady_clock::now();
  rm->BeamOn(N);
  double secs = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
  if (gMode == "trans") {
    auto lv = G4LogicalVolumeStore::GetInstance()->GetVolume("Object");
    auto mat = lv->GetMaterial();
    G4EmCalculator c; double mu = 0;
    for (auto p : {"phot", "compt", "Rayl", "conv"}) mu += c.ComputeCrossSectionPerVolume(gE0, G4Gamma::Definition(), p, mat);
    gOut << "material,density_g_cm3,E_keV,N,plane_all,plane_unscattered_primary,mu_g4_cm_inv,mu_rho_g4_cm2_g,seconds\n"
         << mat->GetName() << "," << mat->GetDensity() / (g / cm3) << "," << gE0 / keV << "," << N << ","
         << gPlaneAll << "," << gPlanePrimary << "," << mu * cm << "," << mu * cm / (mat->GetDensity() / (g / cm3)) << "," << secs << "\n";
  } else {
    std::cerr << "scint hits " << gScintHit << "\n";
  }
  std::cout << "RESULT mode=" << gMode << " E=" << gE0 / keV << "keV N=" << N << " seconds=" << secs
            << " plane_all=" << gPlaneAll << " unscattered=" << gPlanePrimary << " scint_hits=" << gScintHit << std::endl;
  delete rm; return 0;
}
