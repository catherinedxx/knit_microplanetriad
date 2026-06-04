% 3D parametric RUC curve (sin/cos form) -> pick points -> local frames (T,N1,N2)
% -> build fully connected tangent segments (Aend,Bend) + length -> export

clear; clc; close all;
format long

%% -----------------------------
% 1) Define one RUC parametric curve (no spline)
%% -----------------------------
lambda_x = 0.2;
lambda_y = 0.2;
lambda_z = 0.2;

iRUC  = 0;                 % choose ONE RUC (y-shift index)
nFine = 257;               % dense sampling for visualization
w     = linspace(-2, 2, nFine);   % choose endpoints so y=0 at both ends (iRUC=0)

% parametric curve (x(w), y(w), z(w))
x = lambda_x * 0.6  * ( w + sin(pi*w) );
y = lambda_y * 1.0  * cos((pi*w)/2) + 0.3*iRUC;
z = lambda_z * 0.25 * cos(pi*w);

Pfine = [x(:), y(:), z(:)];

% analytic derivatives wrt w (tangent direction)
dxdw = lambda_x * 0.6  * ( 1 + pi*cos(pi*w) );
dydw = lambda_y * 1.0  * ( -(pi/2)*sin((pi*w)/2) );
dzdw = lambda_z * 0.25 * ( -pi*sin(pi*w) );

dPdw_fine = [dxdw(:), dydw(:), dzdw(:)];

% plot dense curve
figure; hold on; grid on;
plot3(Pfine(:,1), Pfine(:,2), Pfine(:,3), 'r-', 'LineWidth', 2);
axis equal; view(3);
xlabel('x'); ylabel('y'); zlabel('z');

%% -----------------------------
% 2) Pick points on the curve and compute tangents at those points
%% -----------------------------
step = 16;                      % pick every "step"-th point
% idx  = 1:step:nFine;
idx = [ ... 
    1, 17, 33, ... 
    57, 65, 73, ... 
    97, 113, 129, ... 
    145, 161, ... 
    185, 193, 201, ... 
    225, 241, 257 ];

P2    = Pfine(idx,:);            % picked points (Nx3)
dPdt  = dPdw_fine(idx,:);        % derivatives wrt w at picked points (Nx3)
T     = dPdt ./ vecnorm(dPdt,2,2); % unit tangent (Nx3)
N     = size(P2,1);

% plot picked points
plot3(P2(:,1),P2(:,2),P2(:,3),'k.','MarkerSize',14);


%% -----------------------------
% 3) Build arbitrary orthonormal directions N1, N2 (per point)
%% -----------------------------
N1 = zeros(N,3);
N2 = zeros(N,3);

for ii = 1:N
    ti = T(ii,:);

    % choose a reference vector not nearly parallel to T
    if abs(ti(1)) < 0.9
        a = [1 0 0];
    else
        a = [0 1 0];
    end

    % Gram-Schmidt: make N1 ⟂ T
    n1 = a - dot(a,ti)*ti;
    n1 = n1 / norm(n1);

    % N2 completes a right-handed orthonormal triad
    n2 = cross(ti, n1);
    n2 = n2 / norm(n2);

    N1(ii,:) = n1;
    N2(ii,:) = n2;
end

%% -----------------------------
% 4) Build fully connected tangent segments using shared junctions
%    Junction J(k) is defined between tangent lines k and k+1
%% -----------------------------
J = zeros(N-1,3);
for k = 1:N-1
    [q1,q2] = closestPtsTwoLines(P2(k,:),   T(k,:), ...
                                 P2(k+1,:), T(k+1,:));
    J(k,:) = 0.5*(q1 + q2);   % midpoint of closest approach (shared junction)
end

Aend   = nan(N,3);
Bend   = nan(N,3);
SegLen = nan(N,1);

for k = 1:N
    pk = P2(k,:);
    tk = T(k,:);

    if k == 1
        % one-sided at first point: from P2(1) to junction J(1) projected on line 1
        Jr = J(1,:);
        sr = dot(Jr - pk, tk);
        Aend(k,:) = pk;
        Bend(k,:) = pk + sr*tk;

    elseif k == N
        % one-sided at last point: from junction J(N-1) projected on line N to P2(N)
        Jl = J(end,:);
        sl = dot(Jl - pk, tk);
        Aend(k,:) = pk + sl*tk;
        Bend(k,:) = pk;

    else
        % two-sided: endpoints come from shared junctions on both sides
        Jl = J(k-1,:);
        Jr = J(k,:);
        sl = dot(Jl - pk, tk);
        sr = dot(Jr - pk, tk);
        Aend(k,:) = pk + sl*tk;
        Bend(k,:) = pk + sr*tk;
    end

    % length of the segment on tangent line k
    SegLen(k) = norm(Bend(k,:) - Aend(k,:));
end

% connection points (shared endpoints after projection)
C = Bend(1:end-1,:);                % should match Aend(2:end,:)
conn = Bend(1:end-1,:) - Aend(2:end,:);
fprintf('mean connection gap = %.3e\n', mean(vecnorm(conn,2,2)));
fprintf('max  connection gap = %.3e\n', max(vecnorm(conn,2,2)));

% plot segments + junctions
figure; hold on; grid on;
plot3(P2(:,1),P2(:,2),P2(:,3),'k.','MarkerSize',14);
plot3(J(:,1),J(:,2),J(:,3),'bo','MarkerSize',6,'LineWidth',1.2);

for k = 1:N
    plot3([Aend(k,1) Bend(k,1)], ...
          [Aend(k,2) Bend(k,2)], ...
          [Aend(k,3) Bend(k,3)], 'g-', 'LineWidth', 2);
end
axis equal; view(3);
xlabel('x'); ylabel('y'); zlabel('z');

%% -----------------------------
% 5 Overlay plot: original curve + connected tangent segments
%% -----------------------------
figure; hold on; grid on;

% original dense curve
plot3(Pfine(:,1), Pfine(:,2), Pfine(:,3), 'r-', 'LineWidth', 2);


% connected tangent segments
for k = 1:N
    plot3([Aend(k,1) Bend(k,1)], ...
          [Aend(k,2) Bend(k,2)], ...
          [Aend(k,3) Bend(k,3)], 'g-', 'LineWidth', 2);
end


axis equal; view(3);
xlabel('x'); ylabel('y'); zlabel('z');


%% -----------------------------
% 6) Export to Excel: one row per point
%% -----------------------------
M = [P2, T, N1, N2, SegLen];

headers = {'P2x','P2y','P2z', ...
           'Tx','Ty','Tz', ...
           'N1x','N1y','N1z', ...
           'N2x','N2y','N2z', ...
           'Length'};

outFile = 'data_parametric_nonuniform.xlsx';
writecell(headers, outFile, 'Sheet', 1, 'Range', 'A1');
writematrix(M,     outFile, 'Sheet', 1, 'Range', 'A2');
disp(['Wrote: ', outFile]);

%% ===========================
% Local function
%% ===========================
function [q1, q2, s, t] = closestPtsTwoLines(p1,u1,p2,u2)
% Closest points between two 3D lines:
%   L1(s) = p1 + s*u1
%   L2(t) = p2 + t*u2

    p1 = p1(:); u1 = u1(:);
    p2 = p2(:); u2 = u2(:);

    if norm(u1) > 0, u1 = u1/norm(u1); end
    if norm(u2) > 0, u2 = u2/norm(u2); end

    w0 = p1 - p2;

    a = dot(u1,u1);
    b = dot(u1,u2);
    c = dot(u2,u2);
    d = dot(u1,w0);
    e = dot(u2,w0);

    denom = a*c - b*b;

    if abs(denom) < 1e-12
        % nearly parallel
        s = 0;
        t = e / c;
    else
        s = (b*e - c*d) / denom;
        t = (a*e - b*d) / denom;
    end

    q1 = (p1 + s*u1).';
    q2 = (p2 + t*u2).';
end
