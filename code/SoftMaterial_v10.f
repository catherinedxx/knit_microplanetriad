C Version 10:
C Selected microplanes use a geometric-effect stiffness switch.
C At small axial strain, these microplanes use the geometric stiffness CGeo.
C After epsN exceeds epsN_sw, the stress switches continuously to the
C base yarn stiffness CBase. Other microplanes use CBase directly.
C Damage is applied after the switch stress is computed.
C PDMS is undamaged through eps_mc, then its remaining modulus drops
C linearly to zero at eps_mf.

      
      subroutine vumat(
     $     nblock, ndir, nshr, nstatev, nfieldv, nprops, lanneal,
     $     stepTime, totalTime, dt, cmname, coordMp, charLength,
     $     props, density, strainInc, relSpinInc,
     $     tempOld, stretchOld, defgradOld, fieldOld,
     $     stressOld, stateOld, enerInternOld, enerInelasOld,
     $     tempNew, stretchNew, defgradNew, fieldNew,
     $     stressNew, stateNew, enerInternNew, enerInelasNew )

      include 'vaba_param.inc'

      dimension props(nprops), density(nblock),
     $coordMp(nblock,*), charLength(nblock),
     $strainInc(nblock,ndir+nshr), relSpinInc(nblock,nshr),
     $tempOld(nblock), stretchOld(nblock,ndir+nshr),
     $defgradOld(nblock,ndir+nshr+nshr), fieldOld(nblock,nfieldv),
     $stressOld(nblock,ndir+nshr), stateOld(nblock,nstatev),
     $enerInternOld(nblock), enerInelasOld(nblock),
     $tempNew(nblock), stretchNew(nblock,ndir+nshr),
     $defgradNew(nblock,ndir+nshr+nshr), fieldNew(nblock,nfieldv),
     $stressNew(nblock,ndir+nshr), stateNew(nblock,nstatev),
     $enerInternNew(nblock), enerInelasNew(nblock)

      character*80 cmname

C --- Material dispatcher
      if (cmname(1:13) .eq. 'PDMS_COTTON_Y') then
         call PDMS_CottonYarn_Material(
     $     nblock, ndir, nshr, nstatev, nfieldv, nprops, lanneal,
     $     stepTime, totalTime, dt, cmname, coordMp, charLength,
     $     props, density, strainInc, relSpinInc,
     $     tempOld, stretchOld, defgradOld, fieldOld,
     $     stressOld, stateOld, enerInternOld, enerInelasOld,
     $     tempNew, stretchNew, defgradNew, fieldNew,
     $     stressNew, stateNew, enerInternNew, enerInelasNew )
      end if

      return
      end subroutine vumat


C======================================================================
C  PDMS + Knitted Cotton Yarn (microplane-triad homogenization)
C======================================================================
      subroutine PDMS_CottonYarn_Material(
     $     nblock, ndir, nshr, nstatev, nfieldv, nprops, lanneal,
     $     stepTime, totalTime, dt, cmname, coordMp, charLength,
     $     props, density, strainInc, relSpinInc,
     $     tempOld, stretchOld, defgradOld, fieldOld,
     $     stressOld, stateOld, enerInternOld, enerInelasOld,
     $     tempNew, stretchNew, defgradNew, fieldNew,
     $     stressNew, stateNew, enerInternNew, enerInelasNew )

      include 'vaba_param.inc'

      dimension props(nprops), density(nblock),
     $coordMp(nblock,*), charLength(nblock),
     $strainInc(nblock,ndir+nshr), relSpinInc(nblock,nshr),
     $tempOld(nblock), stretchOld(nblock,ndir+nshr),
     $defgradOld(nblock,ndir+nshr+nshr), fieldOld(nblock,nfieldv),
     $stressOld(nblock,ndir+nshr), stateOld(nblock,nstatev),
     $enerInternOld(nblock), enerInelasOld(nblock),
     $tempNew(nblock), stretchNew(nblock,ndir+nshr),
     $defgradNew(nblock,ndir+nshr+nshr), fieldNew(nblock,nfieldv),
     $stressNew(nblock,ndir+nshr), stateNew(nblock,nstatev),
     $enerInternNew(nblock), enerInelasNew(nblock)

      character*80 cmname

C ------------------------
C  Indices of STATEV
C  Strain history:
C   STATEV(1-6)
C  Matrix history:
C    STATEV(7) = omega_m        matrix damage variable (0..1)
C
C  Yarn (per triad microplane orientation group):
C    STATEV(7+mu) = omega_y(mu) yarn damage for triad mu, mu=1..ntr
C
C  Total Damage (volumetric Average of yarn and matrix damage):
C    STATEV(8+ntr) = omega_tot
C ------------------------

C ---- constants / sizes
      integer, parameter :: NTENS = 6
      integer, parameter :: MAXTR = 16

C ---- triad geometry (set by PDMS_COTTON_InitTriads)
      integer :: ntr                         ! number of triads actually used (<=MAXTR)
      real*8  :: wtr(MAXTR)                  ! triad weights (sum to 1)
      real*8  :: Q(3,3,MAXTR)                ! direction cosines: columns = [n m l] in global
      real*8  :: QT(3,3,MAXTR)               ! transpose of Q for each triad

C ---- mixture volume fractions
      real*8 :: phi_m                        ! matrix volume fraction
      real*8 :: phi_y                        ! yarn volume fraction (=1-phi_m)

C ---- matrix (PDMS) elastic + damage parameters
      real*8 :: Em0                          ! undamaged matrix Young's modulus
      real*8 :: num                          ! matrix Poisson ratio
      real*8 :: eps_mc                       ! matrix softening initiation strain
      real*8 :: eps_mf                       ! matrix failure strain (stress -> 0)

C ---- yarn (TI) base elastic parameters in local yarn coordinates
C      (1' = yarn axial direction)
      real*8 :: EN
      real*8 :: ET
      real*8 :: nu12
      real*8 :: nu23
      real*8 :: G12

C ---- yarn geometric-effect elastic parameters in local yarn coords
C      These are used only for selected microplanes through the
C      geometric switching law.
      real*8 :: EN_geo
      real*8 :: ET_geo
      real*8 :: nu12_geo
      real*8 :: nu23_geo
      real*8 :: G12_geo

C ---- switching strain for geometric-effect branch
      real*8 :: epsN_sw

C ---- yarn damage parameters (paper-style law applied to yarn)
      real*8 :: Rdrop                        ! Stage-I slope parameter
      real*8 :: epsN_f0                      ! axial strain where first drop begins
      real*8 :: epsN_f1                      ! axial strain where Stage-II begins
      real*8 :: R1, R2, qy                    ! Stage-II parameters
      real*8 :: epsT_f0                      ! transverse damage initiation strain
      real*8 :: epsT_fc                      ! transverse critical strain
C ---- stiffness matrices (Voigt 6x6; tensor shear convention)
      real*8 :: Cmat0(6,6)
      real*8 :: Cmat(6,6)

C ---- yarn local stiffnesses
C      CmuBase_loc : base yarn stiffness
C      CmuGeo_loc  : geometric-effect yarn stiffness
      real*8 :: CmuBase_loc(6,6)
      real*8 :: CmuGeo_loc(6,6)

C ---- per-material-point variables (inside i-loop)
      integer :: i, mu, ic, k
      real*8  :: deps(6)                     ! strain increment from Abaqus
      real*8  :: eps(6)                      ! total strain at end of increment
      real*8  :: sigOld(6), sigNew(6)        ! stresses (old/new) in Voigt
      real*8  :: sig_m(6)                    ! matrix stress contribution
      real*8  :: sig_y(6)                    ! yarn stress contribution (sum over triads)
      real*8  :: sig_mu(6)                   ! triad contribution mapped back to global

      real*8  :: omega_old_m, omega_m        ! matrix damage old/new
      real*8  :: omegaOld_mu, omegaNew_mu    ! yarn triad damage old/new

      real*8  :: eps_eff                     ! effective strain driving matrix damage

      real*8  :: epsTen(3,3)                 ! global strain tensor
      real*8  :: sigTen(3,3)                 ! global stress tensor
      real*8  :: epsLoc(3,3)                 ! local strain tensor (triad coords)
      real*8  :: sigLoc(3,3)                 ! local stress tensor (triad coords)
      real*8  :: epsLocV(6)                  ! local strain in Voigt
      real*8  :: sigLocV(6)                  ! local stress in Voigt

      real*8  :: epsN, epsM, epsL, epsT      ! yarn damage strain measures

      real*8  :: omega_y_avg                 ! weighted average yarn damage over triads
      real*8  :: omega_tot                   ! volumetric average composite damage

C ---- energy bookkeeping (explicit)
      real*8  :: stressPower, rho
      
C ---- selector for which microplanes use geometric-effect switching
C      geoFlag(mu)=1 : use geometric two-branch stiffness switch
C      geoFlag(mu)=0 : use base stiffness only
      integer :: geoFlag(MAXTR)

      
C ---- initialize parameters
      call PDMS_COTTON_InitParams(
     $   phi_m, phi_y, Em0, num, eps_mc, eps_mf,
     $   EN, ET, nu12, nu23, G12,
     $   EN_geo, ET_geo, nu12_geo, nu23_geo, G12_geo,
     $   epsN_sw,
     $   Rdrop, R1, R2, qy, epsN_f0, epsN_f1, epsT_f0, epsT_fc)


C ---- triad geometry
      call PDMS_COTTON_InitTriads(ntr, wtr, Q, QT)
      
C ---- define which microplanes use geometric-effect switching
      call PDMS_COTTON_InitGeoFlag(ntr, geoFlag)
      
C ---- build PDMS stiffnesses
      call BuildIsoStiffness(Em0, num, Cmat0)

C ---- build yarn local stiffness (axis-1 is yarn axial direction)
      call BuildTIStiffness(EN, ET, nu12, nu23, G12, CmuBase_loc)

C ---- build yarn local geometric-effect stiffness
      call BuildTIStiffness(EN_geo, ET_geo, nu12_geo, nu23_geo,
     $                      G12_geo, CmuGeo_loc)


C ---- main block loop
      do i=1,nblock

          
        do k=1,nstatev
           stateNew(i,k) = stateOld(i,k)
        end do

C     -------------------------
C     Read increments (tensor shear)
C     deps = [dE11 dE22 dE33 dE12 dE23 dE13]
C     stress = [S11 S22 S33 S12 S23 S13]
C     -------------------------
         do ic=1,6
            deps(ic)   = strainInc(i,ic)
            sigOld(ic) = stressOld(i,ic)
         end do

C     -------------------------
C     Small-strain accumulation
C     -------------------------
        do k = 1, 6
          eps(k) = stateOld(i,k) + deps(k)
        end do

C     -------------------------
C     Matrix part: damage + stress
C     -------------------------

C      call EffectiveStrain(eps, eps_eff)
      call MaxPrincipalTensileStrain(eps, eps_eff)

      omega_old_m = stateOld(i,7)

      call MatrixDamageLaw(eps_eff,
     $     eps_mc, eps_mf,
     $     omega_old_m, omega_m)

      call ScaleStiffness(Cmat0, (1.0d0 - omega_m), Cmat)
      call LinElasticStress(Cmat, eps, sig_m)

      
       stateNew(i,7) = omega_m

C     -------------------------
C     Yarn part: sum over triads
C     -------------------------
         do ic=1,6
            sig_y(ic) = 0.0d0
         end do

C        Convert global Voigt strain to tensor ONCE (no need inside mu loop)
         call VoigtStrainToTensor(eps, epsTen)

         do mu=1,ntr

C           Rotate strain tensor to triad local axes: epsLoc = QT * epsTen * Q
            call RotateTensorToLocal(epsTen, QT(1,1,mu), Q(1,1,mu), 
     $                                                          epsLoc)

C           Local tensor -> local Voigt strain (tensor shear)
            call TensorToVoigtStrain(epsLoc, epsLocV)

C           Microplane strain measures for yarn damage
            epsN = epsLoc(1,1)
            epsM = epsLoc(2,2)
            epsL = epsLoc(3,3)
            epsT = sqrt(epsM*epsM + epsL*epsL)

C           History variable for yarn damage
            omegaOld_mu = 0.0d0
            omegaOld_mu = stateOld(i,7+mu)

C           Update yarn damage
            call YarnDamageLaw(epsN, epsT,
     $           Rdrop, epsN_f0, epsN_f1, R1, R2, qy,
     $           epsT_f0, epsT_fc,
     $           omegaOld_mu, omegaNew_mu)


C ---------- constitutive choice for current microplane
C            Selected microplanes use geometric switching law;
C            others use only the base yarn stiffness.
            if (geoFlag(mu) .eq. 1) then
               call GeoSwitchYarnStress(CmuBase_loc, CmuGeo_loc,
     $              epsLocV, epsN, epsN_sw, sigLocV)
            else
               call LinElasticStress(CmuBase_loc, epsLocV, sigLocV)
            end if

            do ic = 1, 6
               sigLocV(ic) = (1.0d0 - omegaNew_mu) * sigLocV(ic)
            end do

C           Local Voigt stress -> local tensor stress
            call VoigtStressToTensor(sigLocV, sigLoc)

C           Rotate stress back to global: sigTen = Q * sigLoc * QT
            call RotateTensorToGlobal(sigLoc, Q(1,1,mu), QT(1,1,mu), 
     $                                                        sigTen)

C           Global tensor stress -> global Voigt
            call TensorToVoigtStress(sigTen, sig_mu)

C           Accumulate weighted
            do ic=1,6
               sig_y(ic) = sig_y(ic) + wtr(mu)*sig_mu(ic)
            end do

C           Store updated yarn damage
            stateNew(i,7+mu) = omegaNew_mu

         end do

C     -------------------------
C     Total damage
C     -------------------------
         omega_y_avg = 0.0d0
         do mu = 1, ntr
            omega_y_avg = omega_y_avg + wtr(mu)*stateNew(i,7+mu)
         end do

         omega_tot = phi_m*omega_m + phi_y*omega_y_avg

C        optional clamp for safety
         if (omega_y_avg .lt. 0.0d0) omega_y_avg = 0.0d0
         if (omega_y_avg .gt. 1.0d0) omega_y_avg = 1.0d0
         if (omega_tot   .lt. 0.0d0) omega_tot   = 0.0d0
         if (omega_tot   .gt. 1.0d0) omega_tot   = 1.0d0

C        store total composite damage
         stateNew(i,8+ntr) = omega_tot

C     -------------------------
C     Composite mixture (iso-strain): sigma = phi_m*sigma_m + phi_y*sigma_y
C     -------------------------
         do ic=1,6
            sigNew(ic) = phi_m*sig_m(ic) + phi_y*sig_y(ic)
         end do


C     store total strain
        do k = 1, 6
          stateNew(i,k) = eps(k)
        end do

C     -------------------------
C     Stress output
C     -------------------------
         do ic=1,6
            stressNew(i,ic) = sigNew(ic)
         end do

C     -------------------------
C     Energies (Explicit):
C       enerIntern = internal work per unit mass
C       enerInelas = dissipated (damage) per unit mass
C     -------------------------
          rho = density(i)

C ---- stress power per unit volume (trapezoidal in time)
          stressPower =
     $    0.5d0*(sigOld(1)+sigNew(1))*deps(1) +
     $    0.5d0*(sigOld(2)+sigNew(2))*deps(2) +
     $    0.5d0*(sigOld(3)+sigNew(3))*deps(3) +
     $    2.0d0*0.5d0*(sigOld(4)+sigNew(4))*deps(4) +
     $    2.0d0*0.5d0*(sigOld(5)+sigNew(5))*deps(5) +
     $    2.0d0*0.5d0*(sigOld(6)+sigNew(6))*deps(6)


C ---- internal energy increment per unit mass
          enerInternNew(i) = enerInternOld(i) + stressPower / rho
          enerInelasNew(i) = enerInelasOld(i)
      
      end do

      return
      end subroutine PDMS_CottonYarn_Material


C======================================================================
C  PARAMETER INITIALIZATION
C======================================================================
      subroutine PDMS_COTTON_InitParams(
     $   phi_m, phi_y, Em0, num, eps_mc, eps_mf,
     $   EN, ET, nu12, nu23, G12,
     $   EN_geo, ET_geo, nu12_geo, nu23_geo, G12_geo,
     $   epsN_sw,
     $   Rdrop, R1, R2, qy, epsN_f0, epsN_f1, epsT_f0, epsT_fc)

      include 'vaba_param.inc'

C ---- outputs (all are assigned in this routine)
      real*8 :: phi_m, phi_y
      real*8 :: Em0, num, eps_mc, eps_mf
      real*8 :: EN, ET, nu12, nu23, G12
      real*8 :: EN_geo, ET_geo, nu12_geo, nu23_geo, G12_geo
      real*8 :: epsN_sw
      real*8 :: Rdrop, R1, R2, qy, epsN_f0, epsN_f1, epsT_f0, epsT_fc


C     ---- Volume fractions
      phi_m   = 0.72d0
      phi_y   = 1.0d0 - phi_m

C    ---- PDMS matrix
      Em0     = 1.51d6
      num     = 0.49d0

C    ---- PDMS damage: linear remaining-modulus drop
      eps_mc  = 0.698d0
      eps_mf  = 0.728d0


      
C    ---- Yarn
       EN   = 4.0d8*0.6875d0
       ET   = 4.0d7*0.6875d0 !0.516d8*0.6875d0
       nu12 = 0.30d0
       nu23 = 0.32d0
       G12  = 2.0d7*0.6875d0*0.75d0 !0.216d8*0.6875d0

C    ---- Yarn geometric-effect stiffness
C         Used only for selected microplanes after the switch strain.
       EN_geo   = 1.0d6
       ET_geo   = 0.1d6 !0.129d6
       nu12_geo = 0.30d0
       nu23_geo = 0.32d0
       G12_geo  = 0.05d6*0.75d0 !0.054d6
      

C    ---- switching strain for geometric effect
       epsN_sw = 0.12d0

C    ---- Yarn Damage
        Rdrop   = 9.25d0
        epsN_f0 = 0.40d0
        epsN_f1 = 0.41d0
        R1      = 0.3076d0
        R2      = 200000.00d0
        qy      = 4.25d0
        
       epsT_f0 = 0.189d0
       epsT_fc = 0.3305d0




      
      return
      end subroutine PDMS_COTTON_InitParams

C======================================================================
C  GEOMETRIC-EFFECT MICROPLANE SELECTION
C
C  geoFlag(mu)=1 : this microplane uses the geometric switching law
C  geoFlag(mu)=0 : this microplane uses only the base yarn stiffness
C
C  The indices below select the triads that use only the base yarn
C  stiffness; all other triads use the geometric switching law.
C======================================================================
      subroutine PDMS_COTTON_InitGeoFlag(ntr, geoFlag)
      include 'vaba_param.inc'

      integer, parameter :: MAXTR=16
      integer :: ntr, geoFlag(MAXTR), mu

C ---- initialize all microplanes as geometric by default
      do mu = 1, MAXTR
         geoFlag(mu) = 1
      end do

C ---- deactivate geometric effect for selected microplanes
      geoFlag(1) = 0
      geoFlag(5) = 0
C      geoFlag(6) = 0
      geoFlag(9) = 0
      geoFlag(13) = 0
C      geoFlag(14) = 0


      return
      end subroutine PDMS_COTTON_InitGeoFlag


C======================================================================
C  TRIAD GEOMETRY INITIALIZATION
C======================================================================
      subroutine PDMS_COTTON_InitTriads(ntr, wtr, Q, QT)
      include 'vaba_param.inc'

      integer, parameter :: MAXTR=16
      integer :: ntr, mu, i, j
      real*8  :: wtr(MAXTR), Q(3,3,MAXTR), QT(3,3,MAXTR)
     
      include 'microplane_fortran_nonuniform.inc'

      return
      end subroutine PDMS_COTTON_InitTriads


C======================================================================
C  MatrixDamageLaw  (PDMS linear remaining-modulus drop)
C
C  Usage:
C    call MatrixDamageLaw(eps_eff,
C   $  eps_mc, eps_mf,
C   $  omegaOld, omegaNew)
C
C  Inputs:
C    eps_eff   : CURRENT effective strain e_eff (>=0)
C    eps_mc    : strain where linear modulus reduction begins
C    eps_mf    : failure strain (stress -> 0)
C    omegaOld  : previous damage (STATEV) to enforce irreversibility
C
C  Output:
C    omegaNew  : updated damage, clamped to [0, 1], omegaNew>=omegaOld
C======================================================================
          subroutine MatrixDamageLaw(eps_eff,
     $     eps_mc, eps_mf,
     $     omegaOld, omegaNew)

      include 'vaba_param.inc'
      real*8 :: eps_eff, eps_mc, eps_mf
      real*8 :: omegaOld, omegaNew
      real*8 :: tiny, denom, fac

      tiny = 1.0d-16
      denom = eps_mf - eps_mc

C ---- Undamaged branch followed by a linear remaining-modulus drop.
      if (eps_eff .le. eps_mc) then
         omegaNew = 0.0d0
      else if (denom .le. tiny .or. eps_eff .ge. eps_mf) then
         omegaNew = 1.0d0
      else
C ---- 1 - omega is the line from one at eps_mc to zero at eps_mf.
         fac = (eps_mf - eps_eff) / denom
         omegaNew = 1.0d0 - fac
      end if

C ---- Clamp + irreversibility
      if (omegaNew .lt. 0.0d0)    omegaNew = 0.0d0
      if (omegaNew .gt. 1.0d0)    omegaNew = 1.0d0
      if (omegaNew .lt. omegaOld) omegaNew = omegaOld

      return
      end subroutine MatrixDamageLaw





C======================================================================
C  YarnDamageLaw  (paper-style fiber law applied directly to yarn)
C
C  Usage:
C    call YarnDamageLaw(epsN, epsT,
C   $     Rdrop, epsN_f0, epsN_f1, R1, R2, qy,
C   $     epsT_f0, epsT_fc, omega)
C
C  Inputs:
C    epsN     - axial microplane strain e_N  (local-1 direction)
C    epsT     - transverse effective strain e_T = sqrt(e_M^2 + e_L^2)
C    Rdrop    - parameter R controlling Stage-I slope
C    epsN_f0  - axial strain at first drop begins, e_N^f0
C    epsN_f1  - axial strain at Stage-II begins, e_N^f1
C    R1,R2,qy - Stage-II parameters
C    epsT_f0  - transverse damage initiation strain e_T^f0
C    epsT_fc  - transverse "critical" strain e_T^fc
C
C  Output:
C    omega    - effective yarn damage x_f in [0,1):
C              omega = max(omegaN, omegaT)
C
C======================================================================

      subroutine YarnDamageLaw(epsN, epsT,
     $   Rdrop, epsN_f0, epsN_f1, R1, R2, qy,
     $   epsT_f0, epsT_fc, omegaOld, omegaNew)

      include 'vaba_param.inc'

      real*8 :: epsN, epsT
      real*8 :: Rdrop, epsN_f0, epsN_f1, R1, R2, qy
      real*8 :: epsT_f0, epsT_fc
      real*8 :: omegaOld, omegaNew

      real*8 :: tiny, eN, posN, omegaN, omegaT, denomT

      tiny = 1.0d-16

C ---- axial strain magnitude
      eN = epsN
      
      if (eN .lt. 0.0d0) then
C         No damage in compression
          omegaN = 0.0d0
      else
      
          if (eN .lt. tiny)  eN = tiny

C ---- (A) axial damage omegaN = x_f10
          omegaN = 0.0d0
          if (eN .gt. epsN_f0 + tiny) then
             if (eN .lt. epsN_f1 - tiny) then
C           Stage I: x = (1+R)*(1 - epsN_f0/eN)
                omegaN = (1.0d0 + Rdrop) * (1.0d0 - epsN_f0 / eN)
             else
C           Stage II: x = 1 - (R1/eN)*exp(-R2*<eN-epsN_f0>^q)
                posN = eN - epsN_f0
                if (posN .lt. 0.0d0) posN = 0.0d0
                omegaN = 1.0d0 - (R1 / eN) * exp( -R2 * (posN**qy) )
             end if
          end if

      end if


C ---- (B) transverse damage omegaT = x_f20 (linear ramp)
      omegaT = 0.0d0
      denomT = epsT_fc - epsT_f0
      if (denomT .gt. tiny) then
         if (epsT .gt. epsT_f0) then
            omegaT = (epsT - epsT_f0) / denomT
         end if
      end if

C ---- (C) interaction + irreversibility
      omegaNew = max(omegaN, omegaT)
      if (omegaNew .lt. omegaOld) omegaNew = omegaOld

C ---- Clamp to valid range
      if (omegaNew .lt. 0.0d0)   omegaNew = 0.0d0
      if (omegaNew .gt. 1.0d0)   omegaNew = 1.0d0

      return
      end subroutine YarnDamageLaw



    

C======================================================================
C  BuildIsoStiffness  (3D isotropic linear elasticity, small strain)
C
C  Usage:
C    call BuildIsoStiffness(E, nu, C)
C
C  Inputs:
C    E    - Young's modulus
C    nu   - Poisson's ratio
C
C  Output:
C    C(6,6) - isotropic stiffness matrix in Voigt form, using
C             strain vector  [e11 e22 e33 e12 e23 e13]
C             stress vector  [s11 s22 s33 s12 s23 s13]
C======================================================================
      subroutine BuildIsoStiffness(E, nu, C)
      include 'vaba_param.inc'

      real*8  :: E, nu, C(6,6)
      real*8  :: lam, mu
      integer :: i, j

C ---- Lam� parameters
      mu  = E / (2.0d0*(1.0d0+nu))
      lam = E*nu / ((1.0d0+nu)*(1.0d0-2.0d0*nu))

C ---- zero C
      do i=1,6
         do j=1,6
            C(i,j)=0.0d0
         end do
      end do

C ---- normal-normal block
      C(1,1)=lam+2.d0*mu
      C(2,2)=lam+2.d0*mu
      C(3,3)=lam+2.d0*mu
      C(1,2)=lam
      C(1,3)=lam
      C(2,3)=lam
      C(2,1)=lam
      C(3,1)=lam
      C(3,2)=lam

C ---- shear block
      C(4,4)=2.0d0*mu
      C(5,5)=2.0d0*mu
      C(6,6)=2.0d0*mu

      return
      end subroutine BuildIsoStiffness


C======================================================================
C  BuildTIStiffness  (transversely isotropic yarn stiffness)
C
C  Usage:
C    call BuildTIStiffness(E1, E2, nu12, nu23, G12, C)
C
C  Meaning of axes (local yarn coordinates 1'�2'�3'):
C    1' : yarn (fiber) axial direction
C    2',3' : transverse directions (assumed equivalent for TI)
C
C  Inputs (effective yarn properties in local coordinates):
C    E1    - Young's modulus along 1'
C    E2    - Young's modulus along 2' (and also 3' since TI => E3=E2)
C    nu12  - Poisson's ratio nu_{1'2'} (and nu_{1'3'}=nu12)
C    nu23  - Poisson's ratio nu_{2'3'} (and nu_{3'2'}=nu23)
C    G12   - shear modulus G_{1'2'} (and G_{1'3'}=G12)
C
C  Output:
C    C(6,6) - TI stiffness matrix in Voigt form, using
C             strain vector [e11 e22 e33 e12 e23 e13]
C             stress vector [s11 s22 s33 s12 s23 s13]
C
C======================================================================
      subroutine BuildTIStiffness(E1, E2, nu12, nu23, G12, C)
      include 'vaba_param.inc'

      real*8  :: E1, E2, nu12, nu23, G12, C(6,6)
      real*8  :: E3, nu13, nu21, nu31, nu32
      real*8  :: G23, G13
      real*8  :: detM, Delta
      integer :: i, j

C ---- TI identifications
      E3   = E2
      nu13 = nu12
      nu32 = nu23

C ---- reciprocity relations
      nu21 = nu12 * (E2/E1)
      nu31 = nu13 * (E3/E1)

C ---- shear moduli
      G23 = E2 / (2.0d0 * (1.0d0 + nu23))
      G13 = G12

C ---- initialize C to zero
      do i=1,6
         do j=1,6
            C(i,j) = 0.0d0
         end do
      end do

C ---- Delta = (1/(E1 E2 E3)) * det( [1  -nu21  -nu31;
C                                   -nu12  1    -nu32;
C                                   -nu13 -nu23   1 ] )
      detM = 1.0d0
     $     - nu21*nu12
     $     - nu31*nu13
     $     - nu32*nu23
     $     - nu21*nu32*nu13
     $     - nu31*nu12*nu23

      Delta = detM / (E1 * E2 * E3)

C ---- safety check
      if (abs(Delta) .lt. 1.0d-30) return

C ---- diagonal terms
      C(1,1) = (1.0d0 - nu23*nu32) / (E2*E3*Delta)
      C(2,2) = (1.0d0 - nu13*nu31) / (E1*E3*Delta)
      C(3,3) = (1.0d0 - nu12*nu21) / (E1*E2*Delta)

C ---- coupling terms
      C(1,2) = (nu21 + nu31*nu23) / (E2*E3*Delta)
      C(1,3) = (nu31 + nu21*nu32) / (E2*E3*Delta)
      C(2,3) = (nu32 + nu12*nu31) / (E1*E3*Delta)

C ---- symmetry
      C(2,1) = C(1,2)
      C(3,1) = C(1,3)
      C(3,2) = C(2,3)

C ---- shear terms (Voigt order in this code)
      C(4,4) = 2.0d0*G12
      C(5,5) = 2.0d0*G23
      C(6,6) = 2.0d0*G13

      return
      end subroutine BuildTIStiffness




C======================================================================
C  Basic linear algebra helpers
C======================================================================

C----------------------------------------------------------------------
C  Usage: Compute linear elastic stress in Voigt form:  sig = C * eps
C
C  Inputs:
C    C(6,6)   : stiffness matrix in Voigt order [11 22 33 12 23 13]
C    eps(6)   : strain vector [e11 e22 e33 e12 e23 e13]
C  Outputs:
C    sig(6)   : stress vector [s11 s22 s33 s12 s23 s13] (physical shear)
C----------------------------------------------------------------------
      subroutine LinElasticStress(C, eps, sig)
      include 'vaba_param.inc'
      real*8 :: C(6,6), eps(6), sig(6)
      integer :: i,j

      do i=1,6
         sig(i)=0.0d0
         do j=1,6
            sig(i)=sig(i) + C(i,j)*eps(j)
         end do
      end do

      return
      end subroutine LinElasticStress

C----------------------------------------------------------------------
C  GeoSwitchYarnStress
C
C  Usage:
C    For selected microplanes, compute yarn stress using a two-branch
C    stiffness switch associated with geometric effect.
C
C  Branches:
C    1) Before switching strain epsN_sw:
C         sig = CGeo * eps
C
C    2) After switching strain epsN_sw:
C         sig = CGeo * eps_ref + CBase * (eps - eps_ref)
C
C  Notes:
C    - The reference strain is constructed in the same style as the
C      previous bilinear implementation, so the stress remains continuous
C      at epsN = epsN_sw.
C    - The switch is controlled by the local axial strain epsN.
C    - This routine is called only for microplanes that are marked as
C      geometric-effect microplanes.
C
C  Inputs:
C    CBase(6,6) : original/base yarn stiffness matrix in local coords
C    CGeo(6,6)  : geometric-effect yarn stiffness matrix in local coords
C    epsV(6)    : local strain vector in Voigt order
C    epsN       : local axial strain = epsLoc(1,1)
C    epsN_sw    : switching strain
C
C  Output:
C    sigV(6)    : local stress vector in Voigt order
C----------------------------------------------------------------------
          subroutine GeoSwitchYarnStress(CBase, CGeo, epsV, epsN,
     $     epsN_sw, sigV)
      include 'vaba_param.inc'

      real*8 :: CBase(6,6), CGeo(6,6), epsV(6), sigV(6)
      real*8 :: epsRefV(6), sigRefV(6), depsV(6)
      real*8 :: epsN, epsN_sw, alpha, tiny
      integer :: i

      tiny = 1.0d-16

C ---- use geo set at small strain
      if (epsN .le. epsN_sw) then
         call LinElasticStress(CGeo, epsV, sigV)
         return
      end if

C ---- reference point on the switching surface:
C      scale the WHOLE local strain vector back to epsN = epsN_sw
      alpha = epsN_sw / epsN

      do i = 1, 6
         epsRefV(i) = alpha * epsV(i)
         depsV(i)   = epsV(i) - epsRefV(i)
      end do


C ---- continuous stress:
C      sig = CGeo*epsRef + CBase*(eps-epsRef)
      call LinElasticStress(CGeo,  epsRefV, sigRefV)
      call LinElasticStress(CBase, depsV,   sigV)

      do i = 1, 6
         sigV(i) = sigV(i) + sigRefV(i)
      end do

      return
      end subroutine GeoSwitchYarnStress
      
C----------------------------------------------------------------------
C  Usage: Scale a 6x6 stiffness matrix:  C = scale * C0
C
C  Inputs:
C    C0(6,6)  : base stiffness matrix (e.g., undamaged yarn stiffness)
C    scale    : scalar multiplier (typical use: (1-omega_mu) for a triad)
C  Outputs:
C    C(6,6)   : scaled stiffness matrix
C----------------------------------------------------------------------
      subroutine ScaleStiffness(C0, scale, C)
      include 'vaba_param.inc'
      real*8 :: C0(6,6), C(6,6), scale
      integer :: i,j

      do i=1,6
         do j=1,6
            C(i,j)=scale*C0(i,j)
         end do
      end do

      return
      end subroutine ScaleStiffness


C======================================================================
C  Strain/stress conversions + rotations (consistent with Abaqus VUMAT)
C======================================================================

C----------------------------------------------------------------------
C  Usage: Convert Voigt strain -> 3x3 symmetric tensor
C
C  Inputs:
C    ev(6) : strain in Voigt order [e11 e22 e33 e12 e23 e13]
C  Outputs:
C    et(3,3) : small-strain tensor e_ij (symmetric)
C----------------------------------------------------------------------
      subroutine VoigtStrainToTensor(ev, et)
      include 'vaba_param.inc'
      real*8 :: ev(6), et(3,3)

      et(1,1)=ev(1)
      et(2,2)=ev(2)
      et(3,3)=ev(3)

      et(1,2)=ev(4)
      et(2,1)=et(1,2)

      et(2,3)=ev(5)
      et(3,2)=et(2,3)

      et(1,3)=ev(6)
      et(3,1)=et(1,3)

      return
      end subroutine VoigtStrainToTensor


C----------------------------------------------------------------------
C  Usage: Convert 3x3 symmetric strain tensor -> Voigt strain
C
C  Inputs:
C    et(3,3) : strain tensor e_ij (symmetric)
C  Outputs:
C    ev(6)   : Voigt strain [e11 e22 e33 e12 e23 e13]
C----------------------------------------------------------------------
      subroutine TensorToVoigtStrain(et, ev)
      include 'vaba_param.inc'
      real*8 :: et(3,3), ev(6)

      ev(1)=et(1,1)
      ev(2)=et(2,2)
      ev(3)=et(3,3)

      ev(4)=et(1,2)
      ev(5)=et(2,3)
      ev(6)=et(1,3)

      return
      end subroutine TensorToVoigtStrain


C----------------------------------------------------------------------
C  Usage: Convert Voigt stress -> 3x3 symmetric stress tensor
C
C  Inputs:
C    sv(6) : stress in Voigt order [s11 s22 s33 s12 s23 s13]
C            NOTE: shear components are physical stresses
C  Outputs:
C    st(3,3) : Cauchy stress tensor s_ij (symmetric)
C----------------------------------------------------------------------
      subroutine VoigtStressToTensor(sv, st)
      include 'vaba_param.inc'
      real*8 :: sv(6), st(3,3)

      st(1,1)=sv(1)
      st(2,2)=sv(2)
      st(3,3)=sv(3)

      st(1,2)=sv(4)
      st(2,1)=sv(4)

      st(2,3)=sv(5)
      st(3,2)=sv(5)

      st(1,3)=sv(6)
      st(3,1)=sv(6)

      return
      end subroutine VoigtStressToTensor


C----------------------------------------------------------------------
C  Usage: Convert 3x3 symmetric stress tensor -> Voigt stress
C
C  Inputs:
C    st(3,3) : stress tensor s_ij (symmetric)
C  Outputs:
C    sv(6)   : Voigt stress [s11 s22 s33 s12 s23 s13]
C----------------------------------------------------------------------
      subroutine TensorToVoigtStress(st, sv)
      include 'vaba_param.inc'
      real*8 :: st(3,3), sv(6)

      sv(1)=st(1,1)
      sv(2)=st(2,2)
      sv(3)=st(3,3)

      sv(4)=st(1,2)
      sv(5)=st(2,3)
      sv(6)=st(1,3)

      return
      end subroutine TensorToVoigtStress


C----------------------------------------------------------------------
C  Usage: Rotate a symmetric 2nd-order tensor from global -> local axes
C         Aloc = QT * A * Q  (QT = Q^T)
C
C  Inputs:
C    A(3,3)   : tensor in global coordinates
C    Q(3,3)   : direction cosine matrix (columns = local basis vectors in global)
C    QT(3,3)  : transpose(Q)
C  Outputs:
C    Aloc(3,3): tensor in local coordinates
C----------------------------------------------------------------------
      subroutine RotateTensorToLocal(A, QT, Q, Aloc)
      include 'vaba_param.inc'
      real*8 :: A(3,3), QT(3,3), Q(3,3), Aloc(3,3)
      real*8 :: tmp(3,3)
      integer :: i,j,k

C     tmp = QT * A
      do i=1,3
         do j=1,3
            tmp(i,j)=0.0d0
            do k=1,3
               tmp(i,j)=tmp(i,j)+QT(i,k)*A(k,j)
            end do
         end do
      end do

C     Aloc = tmp * Q
      do i=1,3
         do j=1,3
            Aloc(i,j)=0.0d0
            do k=1,3
               Aloc(i,j)=Aloc(i,j)+tmp(i,k)*Q(k,j)
            end do
         end do
      end do

      return
      end subroutine RotateTensorToLocal


C----------------------------------------------------------------------
C  Usage: Rotate a symmetric 2nd-order tensor from local -> global axes
C         A = Q * Aloc * QT  (QT = Q^T)
C
C  Inputs:
C    Aloc(3,3): tensor in local coordinates
C    Q(3,3)   : direction cosine matrix (columns = local basis vectors in global)
C    QT(3,3)  : transpose(Q)
C  Outputs:
C    A(3,3)   : tensor in global coordinates
C----------------------------------------------------------------------
      subroutine RotateTensorToGlobal(Aloc, Q, QT, A)
      include 'vaba_param.inc'
      real*8 :: Aloc(3,3), Q(3,3), QT(3,3), A(3,3)
      real*8 :: tmp(3,3)
      integer :: i,j,k

C     tmp = Q * Aloc
      do i=1,3
         do j=1,3
            tmp(i,j)=0.0d0
            do k=1,3
               tmp(i,j)=tmp(i,j)+Q(i,k)*Aloc(k,j)
            end do
         end do
      end do

C     A = tmp * QT
      do i=1,3
         do j=1,3
            A(i,j)=0.0d0
            do k=1,3
               A(i,j)=A(i,j)+tmp(i,k)*QT(k,j)
            end do
         end do
      end do

      return
      end subroutine RotateTensorToGlobal



C======================================================================
C  Effective strain measure: eps_eff = (2/3)*sqrt(eps:eps)
C  with eps:eps = e11^2+e22^2+e33^2 + 2*(e12^2+e23^2+e13^2)
C======================================================================
      subroutine EffectiveStrain(epsV, eps_eff)
      include 'vaba_param.inc'
      real*8 :: epsV(6), eps_eff
      real*8 :: eedot
      eedot = epsV(1)*epsV(1) + epsV(2)*epsV(2) + epsV(3)*epsV(3)
      eedot = eedot + 2.0d0*( epsV(4)*epsV(4) + epsV(5)*epsV(5)
     $                       + epsV(6)*epsV(6) )
      eps_eff = (2.0d0/3.0d0) * sqrt(max(eedot,0.0d0))
      return
      end subroutine EffectiveStrain


      
C======================================================================
C  Max principal tensile strain
C
C  Input:
C    epsV = [e11 e22 e33 e12 e23 e13]
C
C  Output:
C    eps_d = max(0, largest principal strain)
C======================================================================
      subroutine MaxPrincipalTensileStrain(epsV, eps_d)
      include 'vaba_param.inc'

      real*8 :: epsV(6), eps_d
      real*8 :: a11, a22, a33, a12, a23, a13
      real*8 :: p1, q, p2, p, r, phi, pi
      real*8 :: b11, b22, b33, b12, b23, b13
      real*8 :: detB
      real*8 :: eig1, eig2, eig3, eigmax
      real*8 :: tiny

      tiny = 1.0d-16
      pi = 4.0d0 * atan(1.0d0)

C ---- strain tensor components
      a11 = epsV(1)
      a22 = epsV(2)
      a33 = epsV(3)
      a12 = epsV(4)
      a23 = epsV(5)
      a13 = epsV(6)

C ---- off-diagonal norm
      p1 = a12*a12 + a23*a23 + a13*a13

C ---- if already diagonal
      if (p1 .le. tiny) then
         eigmax = max(a11, max(a22, a33))
         eps_d = max(eigmax, 0.0d0)
         return
      end if

C ---- mean strain
      q = (a11 + a22 + a33) / 3.0d0

C ---- deviatoric norm
      p2 = (a11-q)*(a11-q)
     $   + (a22-q)*(a22-q)
     $   + (a33-q)*(a33-q)
     $   + 2.0d0*p1

      p = sqrt(p2 / 6.0d0)

      if (p .le. tiny) then
         eigmax = q
         eps_d = max(eigmax, 0.0d0)
         return
      end if

C ---- B = (A - q I) / p
      b11 = (a11 - q) / p
      b22 = (a22 - q) / p
      b33 = (a33 - q) / p
      b12 = a12 / p
      b23 = a23 / p
      b13 = a13 / p

C ---- determinant of B
      detB = b11*b22*b33
     $     + 2.0d0*b12*b23*b13
     $     - b11*b23*b23
     $     - b22*b13*b13
     $     - b33*b12*b12

      r = 0.5d0 * detB

C ---- numerical clamp
      if (r .gt. 1.0d0) r = 1.0d0
      if (r .lt. -1.0d0) r = -1.0d0

      phi = acos(r) / 3.0d0

C ---- eigenvalues of symmetric 3x3 strain tensor
      eig1 = q + 2.0d0*p*cos(phi)
      eig3 = q + 2.0d0*p*cos(phi + 2.0d0*pi/3.0d0)
      eig2 = 3.0d0*q - eig1 - eig3

      eigmax = max(eig1, max(eig2, eig3))

C ---- tensile principal strain only
      eps_d = max(eigmax, 0.0d0)

      return
      end subroutine MaxPrincipalTensileStrain
