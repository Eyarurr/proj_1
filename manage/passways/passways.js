#!/usr/bin/env node

const fs = require('fs');
const THREE = require('three.js-node');
const OBJLoader = require('three-obj-loader');

// OBJLoader фигачит в stdout время загрузки, а нам это не нужно
console.log = function() {};

OBJLoader(THREE);

const program = require('commander');

program
    .version('0.0.1')
    .option('-m, --model <obj_file>', 'Путь до OBJ-файла с моделью.')
    .option(
        '-s, --meta [json_file]',
        'Путь до JSON-файла с метой. Если не задан, то ожидается в stdin.'
    )
    .option(
        '-d, --distance <max_distance>',
        'Максимальное расстояние между соседними скайбоксами. По умолчанию +Infinity.',
        Number.POSITIVE_INFINITY
    )
    .parse(process.argv);

async function checkArgs() {
    let errors = [];
    if (program.model) {
        try {
            await fileExist(program.model);
        } catch (err) {
            const error = `Указанный файл ${program.model} модели не существует.`;
            errors.push(error);
        }
    } else {
        const error = 'Файл модели не задан.';
        errors.push(error);
    }
    if (program.meta) {
        try {
            await fileExist(program.meta);
        } catch (err) {
            const error = `Указанный файл ${program.meta} с метаданными не существует.`;
            errors.push(error);
        }
    }
    return errors.length > 0 ? Promise.reject(errors) : Promise.resolve();
}

async function fileExist(filePath) {
    return new Promise((resolve, reject) => {
        fs.access(filePath, fs.F_OK, err => {
            if (err) {
                return reject(false);
            }
            resolve(true);
        });
    });
}

function parseModel(path) {
    const rawModel = fs.readFileSync(path, 'utf8');
    const loader = new THREE.OBJLoader();
    return loader.parse(rawModel);
}

function applyMaterials(model) {
    let material = new THREE.MeshBasicMaterial({
        color: 0xff0000,
        side: THREE.DoubleSide
    });
    model.traverse(function(child) {
        if (child instanceof THREE.Mesh) {
            child.material = material;
        }
    });
}

async function parseMeta(path) {
    if (path) {
        var rawMeta = fs.readFileSync(path, 'utf8');
        return Promise.resolve(JSON.parse(rawMeta));
    } else {
        return await readStdin();
    }
}

async function readStdin() {
    return new Promise((resolve, reject) => {
        const stdin = process.stdin;
        const inputChunks = [];

        stdin.resume();
        stdin.setEncoding('utf8');

        stdin.on('data', function(chunk) {
            inputChunks.push(chunk);
        });

        stdin.on('end', function() {
            const inputJSON = inputChunks.join('');
            resolve(JSON.parse(inputJSON));
        });
    });
}

/**
 * Обработка меты:
 * - удаление неактивных скайбоксов
 * - преобразование координат в удобный формат
 */
function getSkyboxes(data) {
    const { skyboxes } = data;
    for (skyboxId in skyboxes) {
        const skybox = skyboxes[skyboxId];
        if (skybox.disabled) {
            delete skyboxes[skyboxId];
            continue;
        }
        skybox.pos = new THREE.Vector3().fromArray(skybox.pos);
    }
    return skyboxes;
}

function getPassways(skyboxes, model, maxDistance) {
    const raycaster = new THREE.Raycaster();
    const ids = Object.keys(skyboxes);
    const count = ids.length;
    const passways = [];
    for (let i = 0; i < count; i++) {
        const id1 = ids[i];
        for (let j = i + 1; j < count; j++) {
            const id2 = ids[j];
            const originPos = skyboxes[id1].pos;
            const targetPos = skyboxes[id2].pos;
            let direction = targetPos.clone().sub(originPos);
            const r = direction.length();
            direction = direction.normalize();
            if (r > maxDistance) continue;
            raycaster.set(originPos, direction);
            const result = raycaster.intersectObject(model, true);
            if (Array.isArray(result) && result.length > 0) {
                if (result[0].distance >= r) passways.push([id1, id2]);
            } else {
                passways.push([id1, id2]);
            }
        }
    }
    return passways;
}

async function main() {
    try {
        await checkArgs();
        // console.log(
        //     `Запущено вычисление графа достижимости с параметрами:\n* model path: ${
        //         program.model
        //     }\n* meta path: ${program.meta ? program.meta : 'stdin'}\n* neighbor max distance: ${
        //         program.distance
        //     }`
        // );
        const model = parseModel(program.model);
        applyMaterials(model);
        const meta = await parseMeta(program.meta);
        const skyboxes = getSkyboxes(meta);
        const scene = new THREE.Scene();
        scene.add(model);
        passways = getPassways(skyboxes, model, program.distance);
        process.stdout.write(JSON.stringify(passways));
    } catch (errors) {
        // console.error(errors);
        process.stderr.write(errors);
    }
}

main();
