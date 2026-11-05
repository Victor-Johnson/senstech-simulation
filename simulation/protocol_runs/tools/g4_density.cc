// Print density and composition of Geant4 NIST materials given on the command line.
#include <G4NistManager.hh>
#include <G4Material.hh>
#include <G4SystemOfUnits.hh>
#include <iostream>
int main(int argc, char** argv) {
    for (int i = 1; i < argc; ++i) {
        auto* m = G4NistManager::Instance()->FindOrBuildMaterial(argv[i]);
        if (!m) { std::cout << argv[i] << " not found\n"; continue; }
        std::cout << argv[i] << " density " << m->GetDensity() / (g / cm3) << " g/cm3:";
        for (size_t k = 0; k < m->GetNumberOfElements(); ++k)
            std::cout << " " << m->GetElement(k)->GetSymbol() << " " << m->GetFractionVector()[k];
        std::cout << "\n";
    }
}
